"""LangGraph wrapper for agent orchestration."""

from typing import Dict, Any, TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from ai_service.core import get_logger, get_retrieval_config
from retrieval.hybrid_search import hybrid_search
from ai_service.agents.triager import apply_retrieval_preferences, format_evidence_chunks
from ai_service.llm_client import call_llm_for_triage, call_llm_for_resolution
from ai_service.repositories import IncidentRepository
from ai_service.policy import get_policy_from_config, get_resolution_policy
from ai_service.guardrails import validate_triage_output, validate_resolution_output
from ai_service.core import IncidentNotFoundError, ApprovalRequiredError


logger = get_logger(__name__)


class TriageState(TypedDict):
    """State for triage agent graph."""

    alert: Dict[str, Any]
    context_chunks: Annotated[list, lambda x, y: x + y]  # Accumulate chunks
    triage_output: Dict[str, Any]
    evidence: Dict[str, Any]
    policy_decision: Dict[str, Any]
    incident_id: str
    evidence_warning: Optional[str]


class ResolutionState(TypedDict):
    """State for resolution copilot graph."""

    incident_id: Optional[str]
    alert: Optional[Dict[str, Any]]
    triage_output: Optional[Dict[str, Any]]
    context_chunks: Annotated[list, lambda x, y: x + y]  # Accumulate chunks
    resolution_output: Dict[str, Any]
    evidence: Dict[str, Any]
    policy_decision: Dict[str, Any]
    evidence_warning: Optional[str]
    resolution_evidence_warning: Optional[str]


def create_triage_graph():
    """
    Create LangGraph for triage agent with full node logic.

    Returns:
        Compiled StateGraph for triage workflow
    """

    def retrieve_context_node(state: TriageState) -> TriageState:
        """Node: Retrieve context from knowledge base."""
        alert = state["alert"]
        # Enhance query text for better retrieval
        try:
            from retrieval.query_enhancer import enhance_query
            query_text = enhance_query(alert)
        except Exception as e:
            logger.warning(f"Query enhancement failed, using basic query: {e}")
            query_text = f"{alert.get('title', '')} {alert.get('description', '')}"
        labels = alert.get("labels", {}) or {}
        service_val = labels.get("service") if isinstance(labels, dict) else None
        component_val = labels.get("component") if isinstance(labels, dict) else None

        logger.debug(
            f"LangGraph: Retrieving context for triage - service={service_val}, component={component_val}"
        )

        # Get retrieval config
        retrieval_cfg = (get_retrieval_config() or {}).get("triage", {})
        retrieval_limit = retrieval_cfg.get("limit", 5)
        vector_weight = retrieval_cfg.get("vector_weight", 0.7)
        fulltext_weight = retrieval_cfg.get("fulltext_weight", 0.3)
        rrf_k = retrieval_cfg.get("rrf_k", 60)

        # Retrieve context
        context_chunks = hybrid_search(
            query_text=query_text,
            service=service_val,
            component=component_val,
            limit=retrieval_limit,
            vector_weight=vector_weight,
            fulltext_weight=fulltext_weight,
            rrf_k=rrf_k,
        )

        # Apply retrieval preferences
        context_chunks = apply_retrieval_preferences(context_chunks, retrieval_cfg)

        # Optionally retrieve logs from InfluxDB if configured
        try:
            from retrieval.influxdb_client import get_influxdb_client

            influxdb_client = get_influxdb_client()
            if influxdb_client.is_configured():
                logs = influxdb_client.get_logs_for_context(
                    query_text=query_text, service=service_val, component=component_val, limit=5
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
            logger.debug(f"InfluxDB log retrieval not available or failed: {str(e)}")

        state["context_chunks"] = context_chunks
        return state

    def triage_llm_node(state: TriageState) -> TriageState:
        """Node: Call LLM for triage analysis."""
        alert = state["alert"]
        context_chunks = state["context_chunks"]

        logger.debug("LangGraph: Calling LLM for triage")

        # Call LLM
        triage_output = call_llm_for_triage(alert, context_chunks)
        state["triage_output"] = triage_output

        return state

    def validate_triage_node(state: TriageState) -> TriageState:
        """Node: Validate triage output with guardrails."""
        triage_output = state["triage_output"]

        logger.debug("LangGraph: Validating triage output")

        is_valid, validation_errors = validate_triage_output(triage_output)
        if not is_valid:
            error_msg = f"Triage validation failed: {', '.join(validation_errors)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        return state

    def policy_node(state: TriageState) -> TriageState:
        """Node: Apply policy gate."""
        triage_output = state["triage_output"]

        logger.debug("LangGraph: Applying policy gate")

        policy_decision = get_policy_from_config(triage_output)
        state["policy_decision"] = policy_decision

        return state

    def store_incident_node(state: TriageState) -> TriageState:
        """Node: Store incident in database."""
        alert = state["alert"]
        triage_output = state["triage_output"]
        policy_decision = state["policy_decision"]
        context_chunks = state["context_chunks"]

        logger.debug("LangGraph: Storing incident")

        # Format evidence
        evidence = format_evidence_chunks(context_chunks)

        # Store incident
        repository = IncidentRepository()
        incident_id = repository.create(
            alert=alert,
            triage_output=triage_output,
            policy_band=policy_decision.get("policy_band", "REVIEW"),
            policy_decision=policy_decision,
        )

        state["incident_id"] = incident_id
        state["evidence"] = evidence

        # Check for evidence warning
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
                    state["evidence_warning"] = (
                        "No historical data found in knowledge base. "
                        "Triage performed without context. "
                        "Please ingest historical data for better results."
                    )
                else:
                    state["evidence_warning"] = (
                        f"No matching evidence found for triage. "
                        f"Triage performed with limited context."
                    )
            except Exception:
                state["evidence_warning"] = None

        return state

    # Build graph
    workflow = StateGraph(TriageState)
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.add_node("triage_llm", triage_llm_node)
    workflow.add_node("validate_triage", validate_triage_node)
    workflow.add_node("policy", policy_node)
    workflow.add_node("store_incident", store_incident_node)

    # Define edges
    workflow.set_entry_point("retrieve_context")
    workflow.add_edge("retrieve_context", "triage_llm")
    workflow.add_edge("triage_llm", "validate_triage")
    workflow.add_edge("validate_triage", "policy")
    workflow.add_edge("policy", "store_incident")
    workflow.add_edge("store_incident", END)

    return workflow.compile()


def create_resolution_graph():
    """
    Create LangGraph for resolution copilot with full node logic.

    Returns:
        Compiled StateGraph for resolution workflow
    """

    def get_incident_node(state: ResolutionState) -> ResolutionState:
        """Node: Get or create incident."""
        incident_id = state.get("incident_id")
        alert = state.get("alert")

        repository = IncidentRepository()

        if incident_id:
            try:
                incident = repository.get_by_id(incident_id)
                state["alert"] = incident["raw_alert"]
                state["triage_output"] = incident["triage_output"]
                logger.debug(f"LangGraph: Using existing incident {incident_id}")
            except IncidentNotFoundError as e:
                logger.error(f"Incident not found: {incident_id}")
                raise
        else:
            if not alert:
                raise ValueError("Either incident_id or alert required")

            # Perform triage first
            logger.debug("LangGraph: Performing triage first for resolution")
            from ai_service.agents.triager import _triage_agent_internal

            triage_result = _triage_agent_internal(alert)
            state["triage_output"] = triage_result.get("triage_output", {})
            state["incident_id"] = triage_result.get("incident_id", "")

        return state

    def retrieve_context_node(state: ResolutionState) -> ResolutionState:
        """Node: Retrieve context from knowledge base."""
        alert = state.get("alert") or {}
        triage_output = state.get("triage_output") or {}

        # Enhance query text for better retrieval
        try:
            from retrieval.query_enhancer import enhance_query
            base_query = enhance_query(alert)
            query_text = f"{base_query} resolution steps runbook"
        except Exception as e:
            logger.warning(f"Query enhancement failed, using basic query: {e}")
            query_text = (
                f"{alert.get('title', '')} {alert.get('description', '')} resolution steps runbook"
            )
        labels = alert.get("labels", {}) or {}
        service_val = labels.get("service") if isinstance(labels, dict) else None
        component_val = labels.get("component") if isinstance(labels, dict) else None

        logger.debug(
            f"LangGraph: Retrieving context for resolution - service={service_val}, component={component_val}"
        )

        # Get retrieval config for resolution
        retrieval_config_all = get_retrieval_config() or {}
        resolution_retrieval_cfg = retrieval_config_all.get("resolution", {})
        retrieval_limit = resolution_retrieval_cfg.get("limit", 10)
        vector_weight = resolution_retrieval_cfg.get("vector_weight", 0.7)
        fulltext_weight = resolution_retrieval_cfg.get("fulltext_weight", 0.3)
        use_mmr = resolution_retrieval_cfg.get("use_mmr", False)
        mmr_diversity = resolution_retrieval_cfg.get("mmr_diversity", 0.5)

        # Retrieve context
        from retrieval.hybrid_search import hybrid_search
        
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
            rrf_k = resolution_retrieval_cfg.get("rrf_k", 60)
            context_chunks = hybrid_search(
                query_text=query_text,
                service=service_val,
                component=component_val,
                limit=retrieval_limit,
                vector_weight=vector_weight,
                fulltext_weight=fulltext_weight,
                rrf_k=rrf_k,
            )

        # Apply retrieval preferences
        context_chunks = apply_retrieval_preferences(context_chunks, resolution_retrieval_cfg)

        # Optionally retrieve logs from InfluxDB if configured
        try:
            from retrieval.influxdb_client import get_influxdb_client

            influxdb_client = get_influxdb_client()
            if influxdb_client.is_configured():
                logs = influxdb_client.get_logs_for_context(
                    query_text=query_text, service=service_val, component=component_val, limit=5
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
            logger.debug(f"InfluxDB log retrieval not available or failed: {str(e)}")

        state["context_chunks"] = context_chunks
        return state

    def policy_node(state: ResolutionState) -> ResolutionState:
        """Node: Apply policy gate."""
        triage_output = state.get("triage_output", {})
        incident_id = state.get("incident_id")

        logger.debug("LangGraph: Applying policy gate for resolution")

        # Get policy decision
        repository = IncidentRepository()
        if incident_id:
            try:
                incident = repository.get_by_id(incident_id)
                existing_policy_band = incident.get("policy_band")
            except Exception:
                existing_policy_band = None
        else:
            existing_policy_band = None

        policy_decision = get_resolution_policy(
            triage_output, existing_policy_band=existing_policy_band
        )
        state["policy_decision"] = policy_decision

        return state

    def resolution_llm_node(state: ResolutionState) -> ResolutionState:
        """Node: Call LLM for resolution generation."""
        alert = state.get("alert") or {}
        triage_output = state.get("triage_output", {})
        context_chunks = state["context_chunks"]
        policy_decision = state["policy_decision"]

        logger.debug("LangGraph: Calling LLM for resolution")

        # Call LLM
        resolution_output = call_llm_for_resolution(
            alert=alert,
            triage_output=triage_output,
            context_chunks=context_chunks,
            policy_band=policy_decision.get("policy_band", "REVIEW"),
        )

        # Ensure provenance is populated from context chunks if LLM didn't provide it
        if not resolution_output.get("provenance") and context_chunks:
            resolution_output["provenance"] = [
                {"doc_id": chunk.get("document_id", ""), "chunk_id": chunk.get("chunk_id", "")}
                for chunk in context_chunks[:10]  # Include top chunks
                if chunk.get("chunk_id") and chunk.get("document_id")
            ]

        state["resolution_output"] = resolution_output

        return state

    def validate_resolution_node(state: ResolutionState) -> ResolutionState:
        """Node: Validate resolution output with guardrails."""
        resolution_output = state["resolution_output"]
        context_chunks = state.get("context_chunks", [])
        policy_decision = state.get("policy_decision", {})

        logger.debug("LangGraph: Validating resolution output")

        is_valid, validation_errors = validate_resolution_output(
            resolution_output, context_chunks=context_chunks
        )
        if not is_valid:
            error_msg = f"Resolution validation failed: {', '.join(validation_errors)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Check if approval required
        if policy_decision.get("requires_approval", False):
            incident_id = state.get("incident_id", "")
            raise ApprovalRequiredError(
                f"Resolution requires approval. Policy band: {policy_decision.get('policy_band')}, "
                f"can_auto_apply: {policy_decision.get('can_auto_apply', False)}, "
                f"requires_approval: {policy_decision.get('requires_approval', True)}. "
                f"Please review the triage results for incident {incident_id} and approve before requesting resolution."
            )

        return state

    def store_resolution_node(state: ResolutionState) -> ResolutionState:
        """Node: Store resolution in database."""
        incident_id = state.get("incident_id")
        resolution_output = state["resolution_output"]
        policy_decision = state["policy_decision"]
        context_chunks = state["context_chunks"]
        alert = state.get("alert") or {}

        logger.debug("LangGraph: Storing resolution")

        # Format evidence
        labels = alert.get("labels", {}) or {}
        evidence = format_evidence_chunks(
            context_chunks,
            retrieval_method="hybrid_search",
            retrieval_params={
                "service": labels.get("service") if isinstance(labels, dict) else None,
                "component": labels.get("component") if isinstance(labels, dict) else None,
            },
        )

        # Store resolution
        repository = IncidentRepository()
        policy_band = policy_decision.get("policy_band", "REVIEW")
        repository.update_resolution(
            incident_id=incident_id,
            resolution_output=resolution_output,
            resolution_evidence=evidence,
            policy_band=policy_band,
            policy_decision=policy_decision,
        )

        state["evidence"] = evidence

        # Check for evidence warnings
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
                    state["resolution_evidence_warning"] = (
                        "No historical data found in knowledge base. "
                        "Resolution generated without context. "
                        "Please ingest historical data for better results."
                    )
                else:
                    state["resolution_evidence_warning"] = (
                        f"No matching evidence found for resolution. "
                        f"Resolution generated with limited context."
                    )
            except Exception:
                state["resolution_evidence_warning"] = None

        return state

    # Build graph
    workflow = StateGraph(ResolutionState)
    workflow.add_node("get_incident", get_incident_node)
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.add_node("policy", policy_node)
    workflow.add_node("resolution_llm", resolution_llm_node)
    workflow.add_node("validate_resolution", validate_resolution_node)
    workflow.add_node("store_resolution", store_resolution_node)

    # Define edges
    workflow.set_entry_point("get_incident")
    workflow.add_edge("get_incident", "retrieve_context")
    workflow.add_edge("retrieve_context", "policy")
    workflow.add_edge("policy", "resolution_llm")
    workflow.add_edge("resolution_llm", "validate_resolution")
    workflow.add_edge("validate_resolution", "store_resolution")
    workflow.add_edge("store_resolution", END)

    return workflow.compile()


def run_triage_graph(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run triage graph and return result in expected format.

    Args:
        alert: Alert dictionary

    Returns:
        Dictionary with incident_id, triage, evidence, policy_band, etc.
    """
    graph = create_triage_graph()

    # Initialize state
    initial_state: TriageState = {
        "alert": alert,
        "context_chunks": [],
        "triage_output": {},
        "evidence": {},
        "policy_decision": {},
        "incident_id": "",
        "evidence_warning": None,
    }

    # Run graph
    final_state = graph.invoke(initial_state)

    # Format result (matching expected API response format)
    return {
        "incident_id": final_state["incident_id"],
        "triage": final_state["triage_output"],
        "evidence": final_state["evidence"],
        "evidence_chunks": final_state.get("evidence", {}).get("chunks", []),
        "policy_band": final_state["policy_decision"].get("policy_band", "REVIEW"),
        "policy_decision": final_state["policy_decision"],
        "evidence_warning": final_state.get("evidence_warning"),
        # Include all evidence fields for compatibility
        "triage_evidence": final_state.get("evidence", {}),
    }


def run_resolution_graph(
    incident_id: Optional[str] = None, alert: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run resolution graph and return result in expected format.

    Args:
        incident_id: Optional incident ID
        alert: Optional alert dictionary

    Returns:
        Dictionary with incident_id, resolution, evidence, policy_band, etc.
    """
    graph = create_resolution_graph()

    # Initialize state
    initial_state: ResolutionState = {
        "incident_id": incident_id,
        "alert": alert,
        "triage_output": None,
        "context_chunks": [],
        "resolution_output": {},
        "evidence": {},
        "policy_decision": {},
        "evidence_warning": None,
        "resolution_evidence_warning": None,
    }

    # Run graph
    final_state = graph.invoke(initial_state)

    # Format result (matching expected API response format)
    return {
        "incident_id": final_state["incident_id"],
        "resolution": final_state["resolution_output"],
        "evidence": final_state["evidence"],
        "evidence_chunks": final_state.get("evidence", {}).get("chunks", []),
        "policy_band": final_state["policy_decision"].get("policy_band", "REVIEW"),
        "policy_decision": final_state["policy_decision"],
        "evidence_warning": final_state.get("evidence_warning"),
        "resolution_evidence_warning": final_state.get("resolution_evidence_warning"),
        # Include all evidence fields for compatibility
        "resolution_evidence": final_state.get("evidence", {}),
    }
