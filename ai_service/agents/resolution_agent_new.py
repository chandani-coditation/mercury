"""Resolution Agent - New Format (UI-Ready Steps).

Per architecture: Resolution agent:
- Takes structured triage output ONLY
- Retrieves runbook steps and historical resolutions
- Filters out documentation/context steps
- Orders steps by logical flow (investigation → mitigation → resolution → verification)
- Transforms steps with titles and clean actions
- Outputs UI-ready format with steps array
"""

from typing import Dict, Any, Optional, List
from ai_service.core import get_logger, get_llm_config
from ai_service.models import TriageOutput
from ai_service.repositories import IncidentRepository
from ai_service.core import IncidentNotFoundError
from retrieval.resolution_retrieval import (
    retrieve_runbook_steps,
    retrieve_historical_resolutions,
    retrieve_close_notes_from_signatures,
    get_step_success_stats,
)
from ai_service.ranking import rank_steps
from ai_service.llm_client import get_llm_client, _call_llm_with_retry
from ai_service.prompts import (
    RESOLUTION_RANKING_PROMPT_TEMPLATE,
    RESOLUTION_RANKING_SYSTEM_PROMPT_DEFAULT,
)
from ai_service.guardrails import (
    validate_resolution_no_hallucination,
    validate_no_step_duplication,
    validate_resolution_retrieval_boundaries,
    validate_llm_ranking_no_hallucination,
)
from ai_service.step_transformation import (
    filter_steps,
    order_steps_by_type,
    transform_step_for_ui,
    calculate_estimated_time,
    clean_action_for_ui,
)
import json

logger = get_logger(__name__)


def resolution_agent(triage_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolution Agent - New Format (UI-Ready Steps).
    
    Generates a UI-ready, actionable resolution plan by:
    1. Filtering out documentation/context steps
    2. Ordering steps by logical flow (investigation → mitigation → resolution → verification)
    3. Transforming steps with titles and clean actions
    4. Outputting in new format with steps array
    
    Args:
        triage_output: Triage output dictionary matching TriageOutput model
        
    Returns:
        Dictionary with steps array, estimated_time_minutes, risk_level, confidence, reasoning
    """
    logger.info("Starting resolution agent (new format)")
    
    # Validate triage output structure
    try:
        triage = TriageOutput(**triage_output)
    except Exception as e:
        logger.error(f"Invalid triage output structure: {e}")
        raise ValueError(f"Invalid triage output: {e}")
    
    # Extract runbook IDs and incident signature IDs from triage
    runbook_ids = triage.matched_evidence.runbook_refs or []
    incident_signature_ids = triage.matched_evidence.incident_signatures or []
    incident_signature = triage.incident_signature
    
    logger.debug(
        f"Resolution agent inputs: runbook_ids={runbook_ids}, "
        f"incident_signature_ids={incident_signature_ids}"
    )
    
    # 1. Retrieve runbook steps
    if not runbook_ids:
        logger.warning("No runbook_ids in triage output matched_evidence.runbook_refs")
        # Try to get runbook_ids from evidence if available
        if hasattr(triage_output, 'get') and isinstance(triage_output, dict):
            evidence = triage_output.get("evidence") or {}
            runbook_metadata = evidence.get("runbook_metadata", [])
            if runbook_metadata:
                runbook_ids = [rb.get("runbook_id") for rb in runbook_metadata if rb.get("runbook_id")]
                logger.info(f"Extracted runbook_ids from evidence: {runbook_ids}")
    
    # Retrieve runbook steps using document_id from triage (preferred) or runbook_id (fallback)
    evidence = triage_output.get("evidence", {})
    runbook_metadata = evidence.get("runbook_metadata", [])
    document_ids = [rb.get("document_id") for rb in runbook_metadata if rb.get("document_id")]
    
    # Build query text from triage signals
    query_text_parts = []
    if incident_signature.failure_type:
        query_text_parts.append(incident_signature.failure_type)
    if incident_signature.error_class:
        query_text_parts.append(incident_signature.error_class)
    summary = triage_output.get("summary", "")
    if summary:
        query_text_parts.append(summary[:200])  # Limit length
    query_text = " ".join(query_text_parts) if query_text_parts else None
    
    runbook_steps = retrieve_runbook_steps(
        runbook_ids=runbook_ids if not document_ids else None,
        document_ids=document_ids if document_ids else None,
        query_text=query_text,
        failure_type=incident_signature.failure_type,
        error_class=incident_signature.error_class,
        limit=20
    )
    
    if not runbook_steps:
        logger.warning("No runbook steps found")
        return {
            "steps": [],
            "estimated_time_minutes": 0,
            "risk_level": "high",
            "confidence": 0.0,
            "reasoning": "No runbook steps found for the matched runbooks. Cannot generate recommendations.",
        }
    
    logger.info(f"Retrieved {len(runbook_steps)} runbook steps")
    
    # 2. Filter out documentation/context steps (not actionable)
    filtered_steps = filter_steps(runbook_steps)
    
    if not filtered_steps:
        logger.warning("No actionable steps after filtering documentation/context steps")
        return {
            "steps": [],
            "estimated_time_minutes": 0,
            "risk_level": "high",
            "confidence": 0.0,
            "reasoning": "No actionable steps found in runbooks. All steps were filtered as documentation/context.",
        }
    
    logger.info(f"Filtered to {len(filtered_steps)} actionable steps")
    
    # 3. Retrieve historical resolutions and close notes for context
    historical_resolutions = retrieve_historical_resolutions(
        incident_signature_ids,
        limit=10
    )
    
    close_notes_list = retrieve_close_notes_from_signatures(
        incident_signature_ids,
        limit=10
    )
    
    # 4. Get step success statistics
    step_ids = [step.get("step_id") for step in filtered_steps if step.get("step_id")]
    step_success_stats = get_step_success_stats(step_ids)
    
    # 5. Rank steps by relevance, historical success, and risk
    ranked_steps = rank_steps(
        steps=filtered_steps,
        incident_signature={
            "failure_type": incident_signature.failure_type,
            "error_class": incident_signature.error_class,
        },
        historical_resolutions=historical_resolutions,
        step_success_stats=step_success_stats,
    )
    
    logger.info(f"Ranked {len(ranked_steps)} steps")
    
    # 6. Order steps by logical flow (investigation → mitigation → resolution → verification)
    ordered_steps = order_steps_by_type(ranked_steps)
    
    # 7. Limit to top 5-7 steps for UI
    max_steps = 7
    selected_steps = ordered_steps[:max_steps]
    
    logger.info(f"Selected {len(selected_steps)} steps for resolution plan")
    
    # 8. Transform steps for UI format (with titles, clean actions)
    ui_steps = []
    for idx, step in enumerate(selected_steps, 1):
        ui_step = transform_step_for_ui(step, idx)
        ui_steps.append(ui_step)
    
    # 9. Use LLM to enhance step titles and actions if available
    try:
        llm_recommendations = _call_llm_for_ranking(
            triage_output=triage_output,
            runbook_steps=selected_steps,
            historical_resolutions=historical_resolutions,
            close_notes_list=close_notes_list,
            ranked_recommendations=selected_steps,
        )
        
        llm_recs = llm_recommendations.get("recommendations", [])
        if llm_recs:
            # Create lookup by step_id
            llm_lookup = {rec.get("step_id"): rec for rec in llm_recs if rec.get("step_id")}
            
            # Enhance UI steps with LLM output
            for ui_step in ui_steps:
                step_id = ui_step.get("provenance", {}).get("step_id")
                if step_id and step_id in llm_lookup:
                    llm_rec = llm_lookup[step_id]
                    # Use LLM-enhanced title if available
                    if llm_rec.get("title"):
                        ui_step["title"] = llm_rec["title"]
                    # Use LLM-enhanced action if available and better
                    if llm_rec.get("action") and len(llm_rec.get("action", "")) > len(ui_step.get("action", "")):
                        ui_step["action"] = clean_action_for_ui(llm_rec["action"])
                    # Use LLM-enhanced expected_outcome if available
                    if llm_rec.get("expected_outcome"):
                        ui_step["expected_outcome"] = llm_rec["expected_outcome"]
    except Exception as e:
        logger.warning(f"LLM enhancement failed, using algorithmic output: {e}")
    
    final_steps = ui_steps
    
    # 10. Calculate overall metrics
    overall_confidence = sum(s.get("confidence", 0.0) for s in final_steps) / len(final_steps) if final_steps else 0.0
    
    risk_levels = [s.get("risk_level", "medium") for s in final_steps]
    risk_level = "high" if "high" in risk_levels else ("medium" if "medium" in risk_levels else "low")
    
    # 11. Calculate estimated time
    estimated_time = calculate_estimated_time(selected_steps)
    
    # 12. Build reasoning from triage signals
    summary = triage_output.get("summary", "")
    likely_cause = triage_output.get("likely_cause", "")
    failure_type = incident_signature.failure_type
    error_class = incident_signature.error_class
    
    # Build context-aware reasoning
    if summary and likely_cause:
        reasoning = f"{summary}. {likely_cause}. Steps focus on addressing {failure_type} and {error_class}."
    elif likely_cause:
        reasoning = f"{likely_cause}. Steps focus on resolving {failure_type}/{error_class}."
    else:
        reasoning = f"Steps selected based on relevance to {failure_type}/{error_class} from runbook procedures."
    
    # Ensure reasoning is concise
    if len(reasoning) > 300:
        reasoning = reasoning[:297] + "..."
    
    # 13. Build final output in new format
    result = {
        "steps": [
            {
                "step_number": step.get("step_number"),
                "title": step.get("title"),
                "action": step.get("action"),
                "expected_outcome": step.get("expected_outcome"),
                "risk_level": step.get("risk_level"),
            }
            for step in final_steps
        ],
        "estimated_time_minutes": estimated_time,
        "risk_level": risk_level,
        "confidence": overall_confidence,
        "reasoning": reasoning,
    }
    
    logger.info(
        f"Resolution agent completed: {len(final_steps)} steps, "
        f"confidence={overall_confidence:.2f}, risk={risk_level}, time={estimated_time}min"
    )
    
    return result


def _call_llm_for_ranking(
    triage_output: Dict[str, Any],
    runbook_steps: List[Dict],
    historical_resolutions: List[Dict],
    close_notes_list: List[Dict],
    ranked_recommendations: List[Dict],
) -> Dict[str, Any]:
    """
    Call LLM to enhance step titles and actions.
    
    Args:
        triage_output: Triage output
        runbook_steps: Retrieved runbook steps
        historical_resolutions: Historical resolution records
        close_notes_list: Close notes from matching incidents
        ranked_recommendations: Algorithmically ranked recommendations
        
    Returns:
        LLM output with enhanced recommendations
    """
    client = get_llm_client()
    
    # Get LLM config
    llm_config = get_llm_config()
    resolution_config = llm_config.get("resolution", {})
    
    model = resolution_config.get("model", "gpt-4-turbo-preview")
    temperature = resolution_config.get("temperature", 0.2)
    system_prompt = resolution_config.get(
        "system_prompt", 
        RESOLUTION_RANKING_SYSTEM_PROMPT_DEFAULT
    )
    response_format_type = resolution_config.get("response_format", "json_object")
    max_tokens = resolution_config.get("max_tokens")
    
    # Format runbook steps for prompt
    runbook_steps_text = []
    for step in runbook_steps:
        step_text = (
            f"Step ID: {step.get('step_id')}\n"
            f"Runbook ID: {step.get('runbook_id')}\n"
            f"Condition: {step.get('condition', 'N/A')}\n"
            f"Action: {step.get('action', 'N/A')}\n"
            f"Expected Outcome: {step.get('expected_outcome', 'N/A')}\n"
            f"Risk Level: {step.get('risk_level', 'medium')}\n"
        )
        runbook_steps_text.append(step_text)
    
    runbook_steps_text_str = "\n---\n\n".join(runbook_steps_text)
    
    # Format historical resolutions
    historical_resolutions_text = []
    for hist in historical_resolutions[:5]:
        hist_text = f"Historical: {hist.get('resolution_summary', 'N/A')}"
        historical_resolutions_text.append(hist_text)
    historical_resolutions_text_str = "\n".join(historical_resolutions_text) if historical_resolutions_text else "None"
    
    # Format close notes
    close_notes_text = []
    for note in close_notes_list[:5]:
        note_text = f"Close Note: {note.get('close_notes', 'N/A')}"
        close_notes_text.append(note_text)
    close_notes_text_str = "\n".join(close_notes_text) if close_notes_text else "None"
    
    # Build prompt
    incident_signature = triage_output.get("incident_signature", {})
    failure_type = incident_signature.get("failure_type", "")
    error_class = incident_signature.get("error_class", "")
    severity = triage_output.get("severity", "")
    confidence = triage_output.get("confidence", 0.0)
    matched_evidence = triage_output.get("matched_evidence", {})
    incident_signature_ids = matched_evidence.get("incident_signatures", [])
    runbook_ids = matched_evidence.get("runbook_refs", [])
    
    prompt = RESOLUTION_RANKING_PROMPT_TEMPLATE.format(
        failure_type=failure_type,
        error_class=error_class,
        severity=severity,
        confidence=confidence,
        incident_signature_ids=json.dumps(incident_signature_ids),
        runbook_ids=json.dumps(runbook_ids),
        runbook_steps_text=runbook_steps_text_str,
        historical_resolutions_text=historical_resolutions_text_str,
        close_notes_text=close_notes_text_str,
    )
    
    # Build request
    request_params = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    
    if response_format_type == "json_object":
        request_params["response_format"] = {"type": "json_object"}
    
    if max_tokens:
        request_params["max_tokens"] = max_tokens
    
    # Call LLM with retry logic
    try:
        response = _call_llm_with_retry(client, request_params, "resolution_ranking", model)
        
        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        
        logger.debug("LLM ranking response parsed successfully")
        return result
        
    except Exception as e:
        logger.error(f"LLM ranking failed: {str(e)}", exc_info=True)
        # Fallback to algorithmic ranking
        return {
            "recommendations": ranked_recommendations,
            "overall_confidence": sum(r.get("confidence", 0.0) for r in ranked_recommendations) / len(ranked_recommendations) if ranked_recommendations else 0.0,
            "reasoning": "Ranking completed using algorithmic scoring (LLM ranking unavailable).",
        }

