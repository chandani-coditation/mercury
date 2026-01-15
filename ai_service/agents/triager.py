"""Triager Agent - Analyzes and triages alerts."""

from datetime import datetime
from typing import Dict, Any, Optional, List
from ai_service.llm_client import call_llm_for_triage
from ai_service.repositories import IncidentRepository
from ai_service.policy import get_policy_from_config
from ai_service.guardrails import (
    validate_triage_output,
    validate_triage_no_hallucination,
    validate_triage_retrieval_boundaries,
)
from ai_service.core import get_retrieval_config, get_workflow_config, get_logger, load_config
from retrieval.hybrid_search import triage_retrieval

logger = get_logger(__name__)


def derive_severity_from_impact_urgency(impact: str, urgency: str) -> str:
    """Derive severity from impact and urgency using config mapping."""
    try:
        config = load_config()
        severity_mapping = config.get("field_mappings", {}).get("severity_mapping", {})
        mapping = severity_mapping.get("impact_urgency_to_severity", {})
        default = severity_mapping.get("default_severity", "medium")

        # Extract numeric values (e.g., "3 - Low" -> "3", "1 - High" -> "1")
        impact_val = impact.split()[0] if impact and isinstance(impact, str) else "3"
        urgency_val = urgency.split()[0] if urgency and isinstance(urgency, str) else "3"

        # Create key (e.g., "3-3", "1-1")
        key = f"{impact_val}-{urgency_val}"

        # Look up in mapping
        severity = mapping.get(key, default)

        # Log for debugging severity mapping issues
        logger.info(
            f"Severity mapping: impact='{impact}' -> '{impact_val}', "
            f"urgency='{urgency}' -> '{urgency_val}', key='{key}' -> severity='{severity}'"
        )

        if severity == default and key not in mapping:
            logger.warning(
                f"Severity mapping key '{key}' not found in config. Available keys: {list(mapping.keys())[:10]}... "
                f"Using default '{default}'"
            )

        return severity
    except Exception as e:
        logger.warning(f"Error deriving severity from impact/urgency: {e}. Using default 'medium'")
        return "medium"


def extract_routing_from_alert(alert: Dict[str, Any]) -> Optional[str]:
    """Extract routing (assignment_group) from alert labels."""
    labels = alert.get("labels", {})
    routing = labels.get("assignment_group") or labels.get("routing")
    return routing


def predict_routing_from_evidence(incident_signatures: List[Dict[str, Any]]) -> Optional[str]:
    """
    Predict routing (assignment_group) from matched incident signatures.

    Uses the most common assignment_group from historical incident signatures.
    This is the primary method - alert labels are only used as fallback.

    Args:
        incident_signatures: List of retrieved incident signature chunks with metadata

    Returns:
        Most common assignment_group from signatures, or None if none found
    """
    if not incident_signatures:
        logger.debug("No incident signatures provided for routing prediction")
        return None

    assignment_groups = []
    for sig in incident_signatures:
        metadata = sig.get("metadata", {})
        assignment_group = metadata.get("assignment_group")
        if assignment_group and str(assignment_group).strip():
            assignment_groups.append(str(assignment_group).strip())

    if not assignment_groups:
        logger.warning(
            f"No assignment_group found in {len(incident_signatures)} incident signatures. Available metadata keys: {[list(sig.get('metadata', {}).keys()) for sig in incident_signatures[:2]]}"
        )
        return None

    # Return the most common assignment_group
    from collections import Counter

    counter = Counter(assignment_groups)
    most_common = counter.most_common(1)
    if most_common:
        routing = most_common[0][0]
        logger.info(
            f"Predicted routing from {len(assignment_groups)} signatures: {routing} (appeared {most_common[0][1]} times)"
        )
        return routing

    return None


def predict_impact_urgency_from_evidence(
    incident_signatures: List[Dict[str, Any]],
) -> Optional[tuple[str, str]]:
    """
    Predict impact and urgency from matched incident signatures.

    Uses the most common impact/urgency combination from historical incident signatures.
    This is the primary method - alert labels are only used as fallback.

    Args:
        incident_signatures: List of retrieved incident signature chunks with metadata

    Returns:
        Tuple of (impact, urgency) or None if none found
    """
    if not incident_signatures:
        return None

    impact_urgency_pairs = []
    for sig in incident_signatures:
        metadata = sig.get("metadata", {})
        impact = metadata.get("impact")
        urgency = metadata.get("urgency")
        if impact and urgency:
            impact_urgency_pairs.append((str(impact).strip(), str(urgency).strip()))

    if not impact_urgency_pairs:
        logger.warning(
            f"No impact/urgency found in {len(incident_signatures)} incident signatures. Available metadata keys: {[list(sig.get('metadata', {}).keys()) for sig in incident_signatures[:2]]}"
        )
        return None

    # Find the most common impact/urgency combination
    from collections import Counter

    counter = Counter(impact_urgency_pairs)
    most_common = counter.most_common(1)
    if most_common:
        impact, urgency = most_common[0][0]
        logger.info(
            f"Predicted impact/urgency from {len(impact_urgency_pairs)} signatures: "
            f"impact={impact}, urgency={urgency} "
            f"(appeared {most_common[0][1]} times)"
        )
        return (impact, urgency)

    return None


def predict_severity_from_evidence(incident_signatures: List[Dict[str, Any]]) -> Optional[str]:
    """
    Predict severity from matched incident signatures based on impact/urgency.

    Uses the most common impact/urgency combination from historical incident signatures
    to derive severity. This is the primary method - alert labels are only used as fallback.

    Args:
        incident_signatures: List of retrieved incident signature chunks with metadata

    Returns:
        Predicted severity (critical, high, medium, low) or None if none found
    """
    impact_urgency = predict_impact_urgency_from_evidence(incident_signatures)
    if impact_urgency:
        impact, urgency = impact_urgency
        severity = derive_severity_from_impact_urgency(impact, urgency)
        logger.info(
            f"Derived severity from predicted impact/urgency: {impact}/{urgency} -> {severity}"
        )
        return severity

    return None


def format_evidence_chunks(
    context_chunks: list, retrieval_method: str = "hybrid_search", retrieval_params: dict = None
) -> dict:
    """Format evidence chunks for storage with provenance fields."""
    formatted = {
        "chunks_used": len(context_chunks),
        "chunk_ids": [chunk.get("chunk_id") for chunk in context_chunks if chunk.get("chunk_id")],
        "chunk_sources": [
            chunk.get("doc_title") for chunk in context_chunks if chunk.get("doc_title")
        ],
        "chunks": [],
        "retrieval_method": retrieval_method,
        "retrieval_params": retrieval_params or {},
    }
    type_counts = {}
    for chunk in context_chunks:
        if not chunk.get("chunk_id") and not chunk.get("document_id"):
            continue

        metadata = chunk.get("metadata") or {}
        source_type = (
            chunk.get("doc_type") or metadata.get("doc_type") or metadata.get("source_type")
        )
        if source_type:
            type_counts[source_type] = type_counts.get(source_type, 0) + 1
        if source_type == "incident_signature":
            source_incident_ids = metadata.get("source_incident_ids", [])
            match_count = metadata.get("match_count") or (
                len(source_incident_ids) if source_incident_ids else 0
            )
            metadata["source_incident_ids"] = source_incident_ids
            metadata["match_count"] = match_count

        formatted["chunks"].append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "doc_title": chunk.get("doc_title"),
                "content": chunk.get("content", ""),
                "provenance": {
                    "source_type": source_type,
                    "source_id": chunk.get("document_id"),
                    "service": metadata.get("service"),
                    "component": metadata.get("component"),
                },
                "metadata": metadata,
                "scores": {
                    "vector_score": float(chunk.get("vector_score") or 0.0),
                    "fulltext_score": float(chunk.get("fulltext_score") or 0.0),
                    "rrf_score": float(chunk.get("rrf_score") or 0.0),
                },
            }
        )
    if type_counts:
        parts = [f"{count} {t}" for t, count in sorted(type_counts.items(), key=lambda x: -x[1])]
        formatted["provenance_summary"] = ", ".join(parts)
    return formatted


def apply_retrieval_preferences(context_chunks: list, retrieval_cfg: dict) -> list:
    """Apply retrieval preferences (prefer_types, max_per_type) to context chunks."""
    prefer_types = retrieval_cfg.get("prefer_types", [])
    max_per_type = retrieval_cfg.get("max_per_type", {})

    if prefer_types:
        for ch in context_chunks:
            if ch.get("doc_type") in prefer_types:
                ch["rrf_score"] = (ch.get("rrf_score") or 0.0) + 0.05
        context_chunks = sorted(
            context_chunks, key=lambda c: c.get("rrf_score") or 0.0, reverse=True
        )

    if max_per_type:
        taken = []
        counts = {}
        for ch in context_chunks:
            t = ch.get("doc_type")
            allowed = max_per_type.get(t)
            if allowed is None or counts.get(t, 0) < allowed:
                taken.append(ch)
                counts[t] = counts.get(t, 0) + 1
        context_chunks = taken

    return context_chunks


def triage_agent(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Triager Agent - Analyzes and triages an alert.

    Flow:
    1. Retrieve context from knowledge base
    2. Call LLM for triage
    3. Validate output with guardrails
    4. Apply policy gate
    5. Store incident in database
    6. Return triage output with evidence

    Args:
        alert: Alert dictionary with title, description, labels, etc.

    Returns:
        Dictionary with incident_id, triage output, evidence, and policy information
    """
    return _triage_agent_internal(alert)


def _triage_agent_internal(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Internal triage agent implementation per architecture.
    """
    if isinstance(alert.get("ts"), datetime):
        alert["ts"] = alert["ts"].isoformat()
    elif "ts" not in alert:
        alert["ts"] = datetime.utcnow().isoformat()

    title = alert.get("title", "") or ""
    description = alert.get("description", "") or ""

    import re

    description_lines = description.split("\n")
    first_line = description_lines[0] if description_lines else ""
    first_line_cleaned = re.sub(r"[^\w\s-]", " ", first_line)
    first_line_cleaned = re.sub(r"\s+", " ", first_line_cleaned).strip()

    if first_line_cleaned and len(first_line_cleaned) > 5:
        fulltext_query_text = f"{title} {first_line_cleaned}".strip()
    else:
        fulltext_query_text = title.strip()

    try:
        from retrieval.query_enhancer import enhance_query

        query_text = enhance_query(alert)  # Enhanced query for vector search
    except Exception as e:
        # Fallback to basic query if enhancement fails
        logger.warning(f"Query enhancement failed, using basic query: {e}")
        query_text = fulltext_query_text

    labels = alert.get("labels", {}) or {}
    service_val = labels.get("service") if isinstance(labels, dict) else None
    component_val = labels.get("component") if isinstance(labels, dict) else None

    logger.info(
        f"Starting triage: query_text='{query_text[:150]}...', "
        f"fulltext_query_text='{fulltext_query_text[:150]}...', "
        f"service={service_val}, component={component_val} "
    )

    # Get retrieval config for triage
    retrieval_cfg = (get_retrieval_config() or {}).get("triage", {})
    retrieval_limit = retrieval_cfg.get("limit", 5)
    vector_weight = retrieval_cfg.get("vector_weight", 0.7)
    fulltext_weight = retrieval_cfg.get("fulltext_weight", 0.3)
    use_mmr = retrieval_cfg.get("use_mmr", False)

    # Use specialized triage retrieval (incident signatures + runbook metadata only)
    try:
        # Check if MMR should be used
        if use_mmr:
            from retrieval.hybrid_search import mmr_search

            # MMR requires hybrid_search results first, so we use triage_retrieval then apply MMR
            # For now, use triage_retrieval and note that MMR can be applied to results if needed
            logger.debug(
                f"MMR requested but triage_retrieval doesn't support MMR yet. Using standard retrieval."
            )

        # rrf_k = retrieval_config.get("rrf_k", 60)
        rrf_k = retrieval_cfg.get("rrf_k", 60)
        triage_evidence = triage_retrieval(
            query_text=query_text,
            service=service_val,
            component=component_val,
            limit=retrieval_limit,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight,
            rrf_k=rrf_k,
            fulltext_query_text=fulltext_query_text,  # Use original query for full-text search
        )

        # Validate retrieval boundaries (guardrail: wrong retrieval)
        is_valid_retrieval, retrieval_errors = validate_triage_retrieval_boundaries(triage_evidence)
        if not is_valid_retrieval:
            logger.error(f"Triage retrieval boundary violation: {retrieval_errors}")
            raise ValueError(
                f"Triage retrieval violated architecture boundaries: {', '.join(retrieval_errors)}"
            )

    except Exception as e:
        logger.error(f"Triage retrieval failed: {e}", exc_info=True)
        triage_evidence = {"incident_signatures": [], "runbook_metadata": []}

    incident_signatures = triage_evidence.get("incident_signatures", [])
    runbook_metadata = triage_evidence.get("runbook_metadata", [])

    evidence_warning = None
    has_evidence = len(incident_signatures) > 0 or len(runbook_metadata) > 0
    evidence_status = "success" if has_evidence else "no_evidence"

    if not has_evidence:
        try:
            from db.connection import get_db_connection_context

            with get_db_connection_context() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as count FROM documents")
                result = cur.fetchone()
                doc_count = result["count"] if isinstance(result, dict) else result[0]
                cur.close()
        except Exception as e:
            logger.warning(f"Could not check document count: {e}")
            doc_count = None

        if doc_count is None:
            evidence_warning = (
                "NO EVIDENCE FOUND: Could not verify database state. "
                "Manual review required. Status: FAILED (no historical evidence available)."
            )
            evidence_status = "failed_no_evidence"
        elif doc_count == 0:
            evidence_warning = (
                "NO EVIDENCE FOUND: No historical data in knowledge base. "
                "Please ingest runbooks and historical incidents first using: "
                "`python scripts/data/ingest_runbooks.py` and `python scripts/data/ingest_servicenow_tickets.py`. "
                "Status: FAILED (no historical evidence available). Proceeding with REVIEW and confidence=0.0."
            )
            evidence_status = "failed_no_evidence"
        else:
            evidence_warning = (
                f"NO EVIDENCE FOUND: Database has {doc_count} documents, but none match the alert context. "
                "This may be due to service/component metadata mismatch. "
                "Please align service/component metadata or ingest matching data. "
                "Status: FAILED (no matching historical evidence). Proceeding with REVIEW and confidence=0.0."
            )
            evidence_status = "failed_no_matching_evidence"

    if has_evidence:
        triage_output = call_llm_for_triage(alert, triage_evidence)

        is_valid, validation_errors = validate_triage_output(triage_output)
        if not is_valid:
            logger.error(f"Triage validation failed: {validation_errors}")
            raise ValueError(f"Triage output validation failed: {', '.join(validation_errors)}")

        is_valid_no_hallucination, hallucination_errors = validate_triage_no_hallucination(
            triage_output, triage_evidence
        )
        if not is_valid_no_hallucination:
            logger.error(f"Triage hallucination detected: {hallucination_errors}")
            raise ValueError(
                f"Triage output contains hallucinated content: {', '.join(hallucination_errors)}"
            )

        matched_evidence = triage_output.get("matched_evidence", {})
        if not matched_evidence.get("incident_signatures") and incident_signatures:
            sig_ids = []
            for sig in incident_signatures:
                metadata = sig.get("metadata", {})
                sig_id = metadata.get("incident_signature_id")
                if sig_id:
                    sig_ids.append(sig_id)
            if sig_ids:
                matched_evidence["incident_signatures"] = sig_ids

        if runbook_metadata:
            runbook_ids = [
                rb.get("tags", {}).get("runbook_id")
                for rb in runbook_metadata
                if rb.get("tags", {}).get("runbook_id")
            ]
            if runbook_ids:
                matched_evidence["runbook_refs"] = runbook_ids

        triage_output["matched_evidence"] = matched_evidence

        base_confidence = triage_output.get("confidence", 0.0)

        if base_confidence == 0 and incident_signatures:
            num_matches = len(incident_signatures)
            if num_matches >= 3:
                base_confidence = 0.9
            elif num_matches >= 2:
                base_confidence = 0.8
            elif num_matches >= 1:
                base_confidence = 0.7

        confidence_boost = 0.0
        service_match_quality = "none"
        component_match_quality = "none"

        if incident_signatures:
            top_sig = incident_signatures[0]
            sig_service_boost = top_sig.get("service_match_boost", 0.0)
            sig_component_boost = top_sig.get("component_match_boost", 0.0)

            if sig_service_boost >= 0.15:
                service_match_quality = "exact"
                confidence_boost += 0.1
            elif sig_service_boost >= 0.10:
                service_match_quality = "partial"
                confidence_boost += 0.05

            if sig_component_boost >= 0.10:
                component_match_quality = "exact"
                confidence_boost += 0.05
            elif sig_component_boost >= 0.05:
                component_match_quality = "partial"
                confidence_boost += 0.02
        else:
            alert_service = (
                alert.get("labels", {}).get("service")
                if isinstance(alert.get("labels"), dict)
                else None
            )
            alert_component = (
                alert.get("labels", {}).get("component")
                if isinstance(alert.get("labels"), dict)
                else None
            )

            if runbook_metadata and (alert_service or alert_component):
                # Check match quality from top runbook
                top_rb = runbook_metadata[0]
                rb_service = top_rb.get("service")
                rb_component = top_rb.get("component")

                # Check service match
                if alert_service and rb_service:
                    alert_service_lower = str(alert_service).lower()
                    rb_service_lower = str(rb_service).lower()
                    if alert_service_lower == rb_service_lower:
                        service_match_quality = "exact"
                        confidence_boost += 0.1
                    elif (
                        alert_service_lower in rb_service_lower
                        or rb_service_lower in alert_service_lower
                    ):
                        service_match_quality = "partial"
                        confidence_boost += 0.05

                # Check component match
                if alert_component and rb_component:
                    alert_component_lower = str(alert_component).lower()
                    rb_component_lower = str(rb_component).lower()
                    if alert_component_lower == rb_component_lower:
                        component_match_quality = "exact"
                        confidence_boost += 0.05
                    elif (
                        alert_component_lower in rb_component_lower
                        or rb_component_lower in alert_component_lower
                    ):
                        component_match_quality = "partial"
                        confidence_boost += 0.02

        final_confidence = min(base_confidence + confidence_boost, 1.0)
        triage_output["confidence"] = final_confidence

        likely_cause = None
        if incident_signatures:
            descriptions = []
            symptoms_list = []

            for sig in incident_signatures[:5]:
                metadata = sig.get("metadata", {})
                description = metadata.get("description") or metadata.get("short_description")
                if description and isinstance(description, str) and len(description.strip()) > 20:
                    descriptions.append(description.strip()[:200])

                symptoms = metadata.get("symptoms", [])
                if symptoms and isinstance(symptoms, list):
                    symptoms_list.extend(
                        [s for s in symptoms if isinstance(s, str) and len(s.strip()) > 3]
                    )

            if descriptions:
                likely_cause = descriptions[0][:300]
            elif symptoms_list:
                unique_symptoms = list(dict.fromkeys(symptoms_list))[:3]
                symptom_text = ", ".join(unique_symptoms).replace("_", " ")
                likely_cause = f"Based on historical incident patterns: {symptom_text}."
                likely_cause = likely_cause[:300]

        if likely_cause:
            triage_output["likely_cause"] = likely_cause
        else:
            triage_output["likely_cause"] = "Unknown (no matching historical evidence available)."

        predicted_impact_urgency = predict_impact_urgency_from_evidence(incident_signatures)
        if predicted_impact_urgency:
            impact, urgency = predicted_impact_urgency
            triage_output["impact"] = impact
            triage_output["urgency"] = urgency
            predicted_severity = derive_severity_from_impact_urgency(impact, urgency)
            triage_output["severity"] = predicted_severity
        else:
            labels = alert.get("labels", {})
            impact = labels.get("impact")
            urgency = labels.get("urgency")
            if impact and urgency:
                triage_output["impact"] = impact
                triage_output["urgency"] = urgency
                mapped_severity = derive_severity_from_impact_urgency(impact, urgency)
                triage_output["severity"] = mapped_severity

        predicted_routing = predict_routing_from_evidence(incident_signatures)
        if predicted_routing:
            triage_output["routing"] = predicted_routing
        else:
            routing = extract_routing_from_alert(alert)
            if routing:
                triage_output["routing"] = routing

        category = None
        if incident_signatures:
            for sig in incident_signatures[:3]:
                metadata = sig.get("metadata", {})
                if "category" in metadata:
                    category = metadata.get("category")
                    if category:
                        break
        if not category:
            labels = alert.get("labels", {})
            if isinstance(labels, dict):
                category = labels.get("category")
        if category:
            triage_output["category"] = category
        workflow_cfg = get_workflow_config() or {}
        feedback_before_policy = bool(workflow_cfg.get("feedback_before_policy", False))
        if feedback_before_policy:
            policy_decision = None
            policy_band = "PENDING"
        else:
            policy_decision = get_policy_from_config(triage_output)
            policy_band = policy_decision.get("policy_band", "REVIEW")

        triage_output["policy"] = policy_band

        # Extract affected_services from alert
        affected_services = alert.get("affected_services")
        if affected_services is not None:
            if isinstance(affected_services, str):
                affected_services = [affected_services]
            elif not isinstance(affected_services, list):
                affected_services = [str(affected_services)]
            if len(affected_services) > 0:
                triage_output["affected_services"] = affected_services
        # Also check labels if not in alert directly
        elif isinstance(alert.get("labels"), dict):
            labels = alert.get("labels", {})
            if "affected_services" in labels:
                aff_svc = labels.get("affected_services")
                if isinstance(aff_svc, str):
                    aff_svc = [aff_svc]
                elif not isinstance(aff_svc, list):
                    aff_svc = [str(aff_svc)]
                if len(aff_svc) > 0:
                    triage_output["affected_services"] = aff_svc

        formatted_evidence = format_evidence_chunks(
            incident_signatures,  # Only incident signatures have chunk structure
            retrieval_method="triage_retrieval",
            retrieval_params={
                "query_text": query_text,
                "service": service_val,
                "component": component_val,
                "limit": retrieval_limit,
            },
        )
        formatted_evidence["incident_signatures"] = [
            {
                "chunk_id": sig.get("chunk_id"),
                "document_id": sig.get("document_id"),
                "incident_signature_id": sig.get("metadata", {}).get("incident_signature_id"),
                "failure_type": sig.get("metadata", {}).get("failure_type"),
                "error_class": sig.get("metadata", {}).get("error_class"),
                "metadata": sig.get("metadata", {}),
                "fulltext_score": sig.get("fulltext_score", 0.0),
                "vector_score": sig.get("vector_score", 0.0),
                "rrf_score": sig.get("rrf_score", 0.0),
            }
            for sig in incident_signatures
        ]
        retrieval_config = get_retrieval_config()
        triage_config = retrieval_config.get("triage", {})
        runbook_threshold = float(triage_config.get("runbook_score_threshold", 0.1))

        filtered_runbook_metadata = []
        for rb in runbook_metadata:
            relevance_score = rb.get("relevance_score", 0.0)
            service_boost = rb.get("service_match_boost", 0.0)
            component_boost = rb.get("component_match_boost", 0.0)

            base_fulltext_score = float(relevance_score) if relevance_score else 0.0
            fulltext_score = min(1.0, base_fulltext_score + service_boost + component_boost)

            if fulltext_score >= runbook_threshold:
                filtered_runbook_metadata.append(rb)

        formatted_evidence["runbook_metadata"] = [
            {
                "document_id": rb.get("document_id"),
                "runbook_id": rb.get("tags", {}).get("runbook_id"),
                "title": rb.get("title"),
                "service": rb.get("service"),
                "component": rb.get("component"),
                # Include scores for resolution agent to select top runbook
                "relevance_score": rb.get("relevance_score", 0.0),
                "service_match_boost": rb.get("service_match_boost", 0.0),
                "component_match_boost": rb.get("component_match_boost", 0.0),
            }
            for rb in filtered_runbook_metadata
        ]

        filtered_runbook_count = 0
        for rb in filtered_runbook_metadata:
            relevance_score = rb.get("relevance_score", 0.0)
            service_boost = rb.get("service_match_boost", 0.0)
            component_boost = rb.get("component_match_boost", 0.0)

            base_fulltext_score = float(relevance_score) if relevance_score else 0.0
            fulltext_score = min(1.0, base_fulltext_score + service_boost + component_boost)

            if fulltext_score < runbook_threshold:
                continue

            filtered_runbook_count += 1
            runbook_chunk = {
                "chunk_id": rb.get("document_id"),
                "document_id": rb.get("document_id"),
                "doc_title": rb.get("title", "Runbook"),
                "content": f"Runbook: {rb.get('title', 'Unknown')}\nService: {rb.get('service', 'N/A')}\nComponent: {rb.get('component', 'N/A')}",
                "provenance": {
                    "source_type": "runbook",
                    "source_id": rb.get("document_id"),
                    "service": rb.get("service"),
                    "component": rb.get("component"),
                },
                "metadata": {
                    "doc_type": "runbook",
                    "runbook_id": rb.get("tags", {}).get("runbook_id"),
                    "title": rb.get("title"),
                    "service": rb.get("service"),
                    "component": rb.get("component"),
                },
                "scores": {
                    "vector_score": None,
                    "fulltext_score": fulltext_score,
                    "rrf_score": None,
                },
            }
            formatted_evidence["chunks"].append(runbook_chunk)
            filtered_runbook_count += 1

        if filtered_runbook_metadata:
            try:
                from retrieval.resolution_retrieval import retrieve_runbook_chunks_by_document_id

                document_ids_for_steps = []
                service_val = alert.get("labels", {}).get("service") or alert.get("service")
                if service_val:
                    for rb in filtered_runbook_metadata:
                        if rb.get("service") == service_val and rb.get("document_id"):
                            document_ids_for_steps.append(rb.get("document_id"))
                    for rb in filtered_runbook_metadata:
                        if rb.get("service") != service_val and rb.get("document_id"):
                            if rb.get("document_id") not in document_ids_for_steps:
                                document_ids_for_steps.append(rb.get("document_id"))
                else:
                    for rb in filtered_runbook_metadata:
                        if rb.get("document_id"):
                            document_ids_for_steps.append(rb.get("document_id"))

                if document_ids_for_steps:
                    runbook_steps = retrieve_runbook_chunks_by_document_id(
                        document_ids_for_steps, query_text=query_text, limit=5
                    )
                    for step in runbook_steps:
                        similarity_score = step.get("similarity_score")
                        vector_score = (
                            float(similarity_score) if similarity_score is not None else None
                        )

                        step_chunk = {
                            "chunk_id": step.get("chunk_id"),
                            "document_id": step.get("document_id"),
                            "doc_title": step.get("runbook_title", "Runbook Step"),
                            "content": f"Condition: {step.get('condition', '')}\nAction: {step.get('action', '')}\nExpected Outcome: {step.get('expected_outcome', 'N/A')}",
                            "provenance": {
                                "source_type": "runbook_step",
                                "source_id": step.get("document_id"),
                                "service": step.get("service"),
                                "component": step.get("component"),
                            },
                            "metadata": {
                                "step_id": step.get("step_id"),
                                "runbook_id": step.get("runbook_id"),
                                "runbook_title": step.get("runbook_title"),
                                "risk_level": step.get("risk_level"),
                                "condition": step.get("condition"),
                                "action": step.get("action"),
                                "expected_outcome": step.get("expected_outcome"),
                            },
                            "scores": {
                                "vector_score": vector_score,
                                "fulltext_score": None,
                                "rrf_score": None,
                            },
                        }
                        formatted_evidence["chunks"].append(step_chunk)
                        if step.get("chunk_id"):
                            formatted_evidence["chunk_ids"].append(step.get("chunk_id"))
                        if step.get("runbook_title"):
                            formatted_evidence["chunk_sources"].append(step.get("runbook_title"))
                    formatted_evidence["chunks_used"] = len(formatted_evidence["chunks"])
            except Exception as e:
                logger.warning(f"Failed to add runbook steps to evidence: {e}")

        def get_unified_score(chunk):
            scores = chunk.get("scores", {})
            if scores.get("rrf_score") is not None:
                return scores.get("rrf_score", 0.0)
            if scores.get("vector_score") is not None:
                return scores.get("vector_score", 0.0)
            if scores.get("fulltext_score") is not None:
                return scores.get("fulltext_score", 0.0)
            return 0.0

        formatted_evidence["chunks"].sort(key=get_unified_score, reverse=True)
    else:
        title = alert.get("title", "Unknown alert") if isinstance(alert, dict) else "Unknown alert"

        routing = extract_routing_from_alert(alert)
        labels = alert.get("labels", {})
        impact = labels.get("impact", "3 - Low")
        urgency = labels.get("urgency", "3 - Low")
        severity = derive_severity_from_impact_urgency(impact, urgency)

        no_evidence_confidence = 0.2 if runbook_metadata else 0.0

        triage_output = {
            "incident_signature": {
                "failure_type": "UNKNOWN_FAILURE",
                "error_class": "UNKNOWN_ERROR",
            },
            "matched_evidence": {
                "incident_signatures": [],
                "runbook_refs": [
                    rb.get("tags", {}).get("runbook_id")
                    for rb in runbook_metadata
                    if rb.get("tags", {}).get("runbook_id")
                ],
            },
            "severity": severity,
            "confidence": no_evidence_confidence,
            "policy": "REVIEW",
        }

        if routing:
            triage_output["routing"] = routing

        # Extract affected_services from alert
        affected_services = alert.get("affected_services")
        if affected_services is not None:
            if isinstance(affected_services, str):
                affected_services = [affected_services]
            elif not isinstance(affected_services, list):
                affected_services = [str(affected_services)]
            if len(affected_services) > 0:
                triage_output["affected_services"] = affected_services
        # Also check labels if not already set
        if "affected_services" not in triage_output and isinstance(alert.get("labels"), dict):
            labels = alert.get("labels", {})
            if "affected_services" in labels:
                aff_svc = labels.get("affected_services")
                if isinstance(aff_svc, str):
                    aff_svc = [aff_svc]
                elif not isinstance(aff_svc, list):
                    aff_svc = [str(aff_svc)]
                if len(aff_svc) > 0:
                    triage_output["affected_services"] = aff_svc

        policy_decision = {
            "policy_band": "REVIEW",
            "can_auto_apply": False,
            "requires_approval": True,
            "notification_required": False,
            "rollback_required": False,
            "policy_reason": "No matching evidence; manual review required.",
        }
        policy_band = "REVIEW"

        formatted_evidence = {
            "incident_signatures": [],
            "runbook_metadata": [],
            "retrieval_method": "triage_retrieval",
            "retrieval_params": {
                "query_text": query_text,
                "service": service_val,
                "component": component_val,
                "limit": retrieval_limit,
            },
        }

    repository = IncidentRepository()
    incident_id = repository.create(
        alert=alert,
        triage_output=triage_output,
        triage_evidence=formatted_evidence,
        policy_band=policy_band,
        policy_decision=policy_decision,
    )


    result = {
        "incident_id": incident_id,
        "triage": triage_output,
        "evidence": formatted_evidence,
        "policy_band": policy_band,
        "policy_decision": policy_decision,
        "evidence_warning": evidence_warning,
        "evidence_status": evidence_status,  # "success", "failed_no_evidence", "failed_no_matching_evidence"
        "status": "success" if has_evidence else "failed_no_evidence",  # Overall status
        "evidence_count": {
            "incident_signatures": len(incident_signatures),
            "runbook_metadata": len(runbook_metadata),
            "total": len(incident_signatures) + len(runbook_metadata),
        },
    }

    if evidence_warning:
        result["warning"] = evidence_warning

    return result
