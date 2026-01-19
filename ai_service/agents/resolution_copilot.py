"""Resolution Copilot Agent - Generates resolution steps for incidents."""

from datetime import datetime
from typing import Dict, Any, Optional
from ai_service.llm_client import call_llm_for_triage, call_llm_for_resolution
from ai_service.repositories import IncidentRepository
from ai_service.core import IncidentNotFoundError

# from ai_service.policy import get_policy_from_config, get_resolution_policy
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import validate_triage_output, validate_resolution_output
from ai_service.core import (
    get_retrieval_config,
    get_workflow_config,
    get_logger,
    ApprovalRequiredError,
)
from retrieval.hybrid_search import hybrid_search
from ai_service.agents.triager import format_evidence_chunks, apply_retrieval_preferences

logger = get_logger(__name__)


def resolution_copilot_agent(
    incident_id: Optional[str] = None,
    alert: Optional[Dict[str, Any]] = None,
    skip_approval_check: bool = False,
) -> Dict[str, Any]:
    """
    Resolution Copilot Agent - Generates resolution steps for an incident.

    Args:
        incident_id: Optional incident ID to fetch existing incident
        alert: Optional alert dictionary (used if incident_id not provided)
        skip_approval_check: If True, bypass approval check and generate steps anyway.
                            Used for fallback scenarios where RAG failed.

    Returns:
        Dictionary with incident_id, resolution output, evidence, and policy information
    """
    return _resolution_copilot_agent_internal(incident_id, alert, skip_approval_check)


def _resolution_copilot_agent_internal(
    incident_id: Optional[str] = None,
    alert: Optional[Dict[str, Any]] = None,
    skip_approval_check: bool = False,
) -> Dict[str, Any]:
    """Internal resolution copilot agent implementation (called by resolution_copilot_agent with metrics)."""
    evidence_warning = None
    resolution_evidence_warning = None

    # Get incident
    repository = IncidentRepository()
    if incident_id:
        try:
            incident = repository.get_by_id(incident_id)
        except IncidentNotFoundError as e:
            logger.error(f"Incident not found: {incident_id}")
            raise
        alert_dict = incident["raw_alert"]
        triage_output = incident["triage_output"]
        existing_policy_band = incident.get("policy_band")
        evidence_warning = None
    else:
        if not alert:
            logger.error("Resolution called without incident_id or alert")
            raise ValueError("Either incident_id or alert required")
        alert_dict = alert.copy()
        if isinstance(alert_dict.get("ts"), datetime):
            alert_dict["ts"] = alert_dict["ts"].isoformat()
        elif "ts" not in alert_dict:
            alert_dict["ts"] = datetime.utcnow().isoformat()
        retrieval_config_all = get_retrieval_config()
        if retrieval_config_all is None:
            retrieval_config_all = {}
        triage_retrieval_cfg = retrieval_config_all.get("triage", {})
        triage_limit = triage_retrieval_cfg.get("limit", 5)
        triage_vector_weight = triage_retrieval_cfg.get("vector_weight", 0.7)
        triage_fulltext_weight = triage_retrieval_cfg.get("fulltext_weight", 0.3)

        try:
            from retrieval.query_enhancer import enhance_query

            query_text = enhance_query(alert)
        except Exception as e:
            logger.warning(f"Query enhancement failed, using basic query: {e}")
            query_text = f"{alert.get('title', '')} {alert.get('description', '')}"

        labels = alert.get("labels", {}) or {}

        resolution_config_all = get_retrieval_config() or {}
        resolution_retrieval_cfg = resolution_config_all.get("resolution", {})
        use_mmr = resolution_retrieval_cfg.get("use_mmr", False)
        mmr_diversity = resolution_retrieval_cfg.get("mmr_diversity", 0.5)

        if use_mmr:
            from retrieval.hybrid_search import mmr_search

            context_chunks = mmr_search(
                query_text=query_text,
                service=labels.get("service") if isinstance(labels, dict) else None,
                component=labels.get("component") if isinstance(labels, dict) else None,
                limit=triage_limit,
                diversity=mmr_diversity,
            )
        else:
            triage_retrieval_cfg = retrieval_config_all.get("triage", {})
            triage_rrf_k = triage_retrieval_cfg.get("rrf_k", 60)
            context_chunks = hybrid_search(
                query_text=query_text,
                service=labels.get("service") if isinstance(labels, dict) else None,
                component=labels.get("component") if isinstance(labels, dict) else None,
                limit=triage_limit,
                vector_weight=triage_vector_weight,
                fulltext_weight=triage_fulltext_weight,
                rrf_k=triage_rrf_k,
            )

        if len(context_chunks) == 0:
            from db.connection import get_db_connection_context

            try:
                with get_db_connection_context() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) as count FROM documents")
                    result = cur.fetchone()
                    doc_count = result["count"] if isinstance(result, dict) else result[0]
                    cur.close()

                if doc_count == 0:
                    evidence_warning = (
                        "No historical data found in knowledge base. "
                        "Resolution generated without context. "
                        "Please ingest historical data (alerts, incidents, runbooks, logs) for better results. "
                        "Use: python scripts/data/ingest_data.py --dir <data_directory>"
                    )
                    logger.warning(evidence_warning)
                else:
                    evidence_warning = (
                        f"No matching evidence found for resolution. "
                        f"Database has {doc_count} documents, but none match the context. "
                        "Resolution generated without relevant historical evidence. "
                        "Please ensure relevant historical data is ingested for better results."
                    )
                    logger.warning(evidence_warning)
            except Exception as e:
                evidence_warning = (
                    f"Cannot verify database state: {e}. Proceeding without evidence validation."
                )
                logger.warning(evidence_warning)

        triage_output = call_llm_for_triage(alert_dict, context_chunks)

        is_valid, validation_errors = validate_triage_output(triage_output)
        if not is_valid:
            logger.error(f"Triage validation failed during resolution: {validation_errors}")
            raise ValueError(f"Triage output validation failed: {', '.join(validation_errors)}")

        policy_decision = get_policy_from_config(triage_output)
        existing_policy_band = policy_decision.get("policy_band", "REVIEW")

        incident_id = repository.create(
            alert=alert_dict,
            triage_output=triage_output,
            policy_band=existing_policy_band,
            policy_decision=policy_decision,
        )

    workflow_cfg = get_workflow_config() or {}

    if not existing_policy_band or existing_policy_band == "PENDING":
        policy_decision = get_policy_from_config(triage_output)
        existing_policy_band = policy_decision.get("policy_band", "REVIEW")
        try:
            repository.update_policy(incident_id, existing_policy_band, policy_decision)
        except Exception as e:
            logger.warning(f"Failed to update policy: {str(e)}")

    if existing_policy_band and existing_policy_band != "PENDING":
        incident = repository.get_by_id(incident_id)
        existing_policy_band = incident.get("policy_band") or existing_policy_band
        triage_output = incident.get("triage_output") or triage_output
        stored_policy_decision = incident.get("policy_decision")
        if stored_policy_decision:
            can_auto_apply = stored_policy_decision.get("can_auto_apply", False)
            requires_approval = stored_policy_decision.get("requires_approval", True)
        else:
            policy_decision = get_policy_from_config(triage_output)
            can_auto_apply = policy_decision.get("can_auto_apply", False)
            requires_approval = policy_decision.get("requires_approval", True)
    else:
        policy_decision = get_policy_from_config(triage_output)
        can_auto_apply = policy_decision.get("can_auto_apply", False)
        requires_approval = policy_decision.get("requires_approval", True)
        existing_policy_band = policy_decision.get("policy_band", "REVIEW")

    if not skip_approval_check and (not can_auto_apply or requires_approval):
        error_msg = (
            f"User approval required before generating resolution. "
            f"Policy band: {existing_policy_band} (from configuration), "
            f"can_auto_apply: {can_auto_apply}, requires_approval: {requires_approval}. "
            f"Please review the triage results for incident {incident_id} and approve before requesting resolution."
        )
        logger.info(error_msg)
        raise ApprovalRequiredError(error_msg)

    # Get retrieval config for resolution
    retrieval_config_all = get_retrieval_config()
    if retrieval_config_all is None:
        retrieval_config_all = {}
    retrieval_config = retrieval_config_all.get("resolution", {})
    retrieval_limit = retrieval_config.get("limit", 10)
    vector_weight = retrieval_config.get("vector_weight", 0.6)
    fulltext_weight = retrieval_config.get("fulltext_weight", 0.4)

    try:
        from retrieval.query_enhancer import enhance_query

        base_query = enhance_query(alert_dict)
        query_text = f"{base_query} resolution steps runbook"
    except Exception as e:
        logger.warning(f"Query enhancement failed, using basic query: {e}")
        query_text = f"{alert_dict.get('title', '')} {alert_dict.get('description', '')} resolution steps runbook"

    labels = alert_dict.get("labels") or {}

    service_val = labels.get("service") if isinstance(labels, dict) else None
    component_val = labels.get("component") if isinstance(labels, dict) else None
    use_mmr = retrieval_config.get("use_mmr", False)
    mmr_diversity = retrieval_config.get("mmr_diversity", 0.5)

    if use_mmr:
        from retrieval.hybrid_search import mmr_search

        context_chunks = mmr_search(
            query_text=query_text,
            service=service_val,
            component=component_val,
            limit=retrieval_limit,
            diversity=mmr_diversity,
        )
    else:
        rrf_k = retrieval_config.get("rrf_k", 60)
        context_chunks = hybrid_search(
            query_text=query_text,
            service=service_val,
            component=component_val,
            limit=retrieval_limit,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight,
            rrf_k=rrf_k,
        )

    context_chunks = apply_retrieval_preferences(context_chunks, retrieval_config)

    try:
        from retrieval.influxdb_client import get_influxdb_client

        influxdb_client = get_influxdb_client()
        if influxdb_client.is_configured():
            logs = influxdb_client.get_logs_for_context(
                query_text=query_text,
                service=service_val,
                component=component_val,
                limit=5,
            )
            for log_content in logs:
                if log_content:
                    context_chunks.append(
                        {
                            "chunk_id": f"influxdb_log_{len(context_chunks)}",
                            "content": f"[Log Entry]\n{log_content}",
                            "doc_type": "log",
                            "source": "influxdb",
                        }
                    )
    except Exception as e:
        pass

    workflow_config = get_workflow_config() or {}
    resolution_config = workflow_config.get("resolution", {})
    allow_resolution_without_context = (
        resolution_config.get("allow_resolution_without_context", False)
        if resolution_config
        else False
    )

    MIN_REQUIRED_CHUNKS = 1

    if len(context_chunks) < MIN_REQUIRED_CHUNKS:
        from db.connection import get_db_connection_context

        try:
            with get_db_connection_context() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as count FROM documents")
                result = cur.fetchone()
                doc_count = result["count"] if isinstance(result, dict) else result[0]
                cur.close()

            if doc_count == 0:
                if allow_resolution_without_context:
                    warning_msg = (
                        "No historical data found in knowledge base. "
                        "Generating resolution with low confidence. "
                        "Please ingest runbooks and historical incidents for better results. "
                        "Use: python scripts/data/ingest_runbooks.py and python scripts/data/ingest_servicenow_tickets.py"
                    )
                    logger.warning(warning_msg)
                    resolution_evidence_warning = warning_msg
                else:
                    error_msg = (
                        "Cannot generate resolution without context. "
                        "No historical data found in knowledge base. "
                        "Please ingest runbooks and historical incidents first. "
                        "Use: python scripts/data/ingest_runbooks.py and python scripts/data/ingest_servicenow_tickets.py"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)
            else:
                if allow_resolution_without_context:
                    warning_msg = (
                        f"Database has {doc_count} documents, but none match the resolution context. "
                        "Generating resolution with low confidence. "
                        "This may be due to metadata mismatch (service/component). "
                        "Please ensure relevant runbooks are ingested with matching metadata, "
                        "or adjust the alert labels to match existing document metadata."
                    )
                    logger.warning(warning_msg)
                    resolution_evidence_warning = warning_msg
                else:
                    error_msg = (
                        f"Cannot generate resolution without context. "
                        f"Database has {doc_count} documents, but none match the resolution context. "
                        "Resolution requires runbooks or similar historical incidents. "
                        "This may be due to metadata mismatch (service/component filters). "
                        "Please ensure relevant runbooks are ingested with matching metadata, "
                        "or adjust the alert labels to match existing document metadata. "
                        "Alternatively, enable 'allow_resolution_without_context' in workflow config for graceful degradation."
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)
        except ValueError:
            if not allow_resolution_without_context:
                raise
            logger.warning(
                "Resolution context validation failed, but graceful degradation enabled. Continuing with low confidence."
            )
            resolution_evidence_warning = (
                "No matching context found, generating resolution with low confidence."
            )
        except Exception as e:
            if allow_resolution_without_context:
                warning_msg = (
                    f"Cannot verify database state: {e}. Proceeding with low confidence resolution."
                )
                logger.warning(warning_msg)
                resolution_evidence_warning = warning_msg
            else:
                error_msg = (
                    f"Cannot verify database state: {e}. Cannot proceed without context validation."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

    resolution_output = call_llm_for_resolution(alert_dict, triage_output, context_chunks)

    if not resolution_output.get("provenance"):
        if context_chunks:
            resolution_output["provenance"] = [
                {"doc_id": chunk.get("document_id", ""), "chunk_id": chunk.get("chunk_id", "")}
                for chunk in context_chunks[:10]
                if chunk.get("chunk_id") and chunk.get("document_id")
            ]
        else:
            logger.warning(
                "No provenance and no context chunks - this should not happen after validation"
            )
            resolution_output["provenance"] = []
    if resolution_output.get("provenance"):
        valid_provenance = []
        context_chunk_ids = {
            chunk.get("chunk_id") for chunk in context_chunks if chunk.get("chunk_id")
        }
        context_doc_ids = {
            chunk.get("document_id") for chunk in context_chunks if chunk.get("document_id")
        }

        for prov in resolution_output["provenance"]:
            prov_chunk_id = prov.get("chunk_id")
            prov_doc_id = prov.get("doc_id")
            if prov_chunk_id in context_chunk_ids and prov_doc_id in context_doc_ids:
                valid_provenance.append(prov)
            else:
                logger.warning(
                    f"Invalid provenance reference: chunk_id={prov_chunk_id}, doc_id={prov_doc_id} "
                    f"not found in context chunks"
                )

        if not valid_provenance and context_chunks:
            resolution_output["provenance"] = [
                {"doc_id": chunk.get("document_id", ""), "chunk_id": chunk.get("chunk_id", "")}
                for chunk in context_chunks[:10]
                if chunk.get("chunk_id") and chunk.get("document_id")
            ]
        else:
            resolution_output["provenance"] = valid_provenance

    if "estimated_time_minutes" not in resolution_output:
        resolution_output["estimated_time_minutes"] = None
    if "risk_level" not in resolution_output:
        resolution_output["risk_level"] = None
    if "requires_approval" not in resolution_output:
        resolution_output["requires_approval"] = None

    is_valid, validation_errors = validate_resolution_output(
        resolution_output, context_chunks=context_chunks
    )
    if not is_valid:
        logger.error(f"Resolution validation failed: {validation_errors}")
        raise ValueError(f"Resolution output validation failed: {', '.join(validation_errors)}")

    if incident_id:
        incident = repository.get_by_id(incident_id)
        policy_decision = incident.get("policy_decision", {}) if incident else {}

    if not policy_decision:
        severity = triage_output.get("severity", "medium")
        policy_decision = get_policy_from_config(triage_output)

    policy_band = existing_policy_band or policy_decision.get("policy_band", "REVIEW")

    resolution_evidence = format_evidence_chunks(
        context_chunks,
        retrieval_method="hybrid_search",
        retrieval_params={
            "query_text": query_text,
            "service": labels.get("service") if isinstance(labels, dict) else None,
            "component": labels.get("component") if isinstance(labels, dict) else None,
            "limit": retrieval_limit,
        },
    )

    repository.update_resolution(
        incident_id=incident_id,
        resolution_output=resolution_output,
        resolution_evidence=resolution_evidence,
        policy_band=policy_band,
        policy_decision=policy_decision,
    )

    result = {
        "incident_id": incident_id,
        "resolution": resolution_output,
        "policy": policy_decision,
        "policy_band": policy_band,
        "context_chunks_used": len(context_chunks),
        "evidence_chunks": resolution_evidence,
    }

    has_resolution_evidence = len(context_chunks) > 0
    resolution_status = "success" if has_resolution_evidence else "failed_no_evidence"

    if resolution_evidence_warning:
        if "No historical data" in resolution_evidence_warning:
            resolution_evidence_warning = (
                "NO EVIDENCE FOUND: No historical data in knowledge base. "
                "Please ingest runbooks and historical incidents first using: "
                "`python scripts/data/ingest_runbooks.py` and `python scripts/data/ingest_servicenow_tickets.py`. "
                "Status: FAILED (no historical evidence available). "
                "Resolution generated with low confidence."
            )
            resolution_status = "failed_no_evidence"
        elif "none match" in resolution_evidence_warning.lower():
            resolution_evidence_warning = (
                f"NO EVIDENCE FOUND: {resolution_evidence_warning} "
                "This may be due to service/component metadata mismatch. "
                "Status: FAILED (no matching historical evidence). "
                "Resolution generated with low confidence."
            )
            resolution_status = "failed_no_matching_evidence"
        else:
            resolution_evidence_warning = (
                f"{resolution_evidence_warning} Status: {resolution_status.upper()}."
            )

    if evidence_warning:
        result["evidence_warning"] = evidence_warning
        result["evidence_status"] = (
            "failed_no_evidence" if "NO EVIDENCE" in evidence_warning else "success"
        )

    if resolution_evidence_warning:
        result["resolution_evidence_warning"] = resolution_evidence_warning
        result["resolution_evidence_status"] = resolution_status

    result["status"] = "success" if has_resolution_evidence else "failed_no_evidence"
    result["evidence_count"] = {
        "context_chunks": len(context_chunks),
        "has_evidence": has_resolution_evidence,
    }

    if resolution_evidence_warning:
        result["warning"] = resolution_evidence_warning
    elif evidence_warning:
        result["warning"] = evidence_warning

    return result
