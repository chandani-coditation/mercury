"""Resolution Agent - Per Architecture Document.

Per architecture: Resolution agent:
- Takes structured triage output ONLY
- Retrieves runbook steps and historical resolutions
- Ranks steps by relevance and historical success
- Assembles ordered recommendations
- Does NOT invent new steps
- Every recommendation MUST have provenance
- Does NOT change incident classification
"""

from typing import Dict, Any, Optional, List
from ai_service.core import get_logger, get_llm_config
from ai_service.models import TriageOutput, ResolutionOutput
from ai_service.repositories import IncidentRepository
from ai_service.core import IncidentNotFoundError
from retrieval.resolution_retrieval import (
    retrieve_runbook_steps,
    retrieve_historical_resolutions,
    get_step_success_stats,
)
from ai_service.ranking import rank_steps, assemble_recommendations
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
import json

logger = get_logger(__name__)


def resolution_agent(triage_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolution Agent - Per Architecture Document.
    
    Per architecture:
    - Input: Structured triage output ONLY
    - Retrieves: Runbook steps (by runbook_id) and historical resolutions
    - Ranks: Steps by relevance, historical success, and risk
    - Output: Ordered recommendations with provenance
    
    Args:
        triage_output: Triage output dictionary matching TriageOutput model
        
    Returns:
        Dictionary with recommendations, overall_confidence, risk_level, reasoning
    """
    logger.info("Starting resolution agent (per architecture)")
    
    # Validate triage output structure
    try:
        triage = TriageOutput(**triage_output)
    except Exception as e:
        logger.error(f"Invalid triage output structure: {e}")
        raise ValueError(f"Invalid triage output: {e}")
    
    # Extract runbook IDs and incident signature IDs from triage
    runbook_ids = triage.matched_evidence.runbook_refs
    incident_signature_ids = triage.matched_evidence.incident_signatures
    incident_signature = triage.incident_signature
    
    logger.debug(
        f"Resolution agent inputs: runbook_ids={runbook_ids}, "
        f"incident_signature_ids={incident_signature_ids}"
    )
    
    # 1. Retrieve runbook steps
    runbook_steps = retrieve_runbook_steps(runbook_ids)
    
    # Validate retrieval boundaries (guardrail: wrong retrieval)
    is_valid_retrieval, retrieval_errors = validate_resolution_retrieval_boundaries(
        retrieved_runbook_steps=runbook_steps,
        retrieved_historical_resolutions=[],  # Not retrieved yet
        expected_runbook_ids=runbook_ids,
        expected_incident_signature_ids=incident_signature_ids,
    )
    if not is_valid_retrieval:
        logger.error(f"Resolution retrieval boundary violation: {retrieval_errors}")
        raise ValueError(f"Resolution retrieval violated architecture boundaries: {', '.join(retrieval_errors)}")
    
    if not runbook_steps:
        logger.warning(
            f"No runbook steps found for runbook_ids: {runbook_ids}. "
            "Cannot generate recommendations without steps."
        )
        return {
            "recommendations": [],
            "overall_confidence": 0.0,
            "risk_level": "high",
            "reasoning": "No runbook steps found for the matched runbooks. Cannot generate recommendations.",
        }
    
    logger.info(f"Retrieved {len(runbook_steps)} runbook steps")
    
    # 2. Retrieve historical resolutions
    historical_resolutions = retrieve_historical_resolutions(
        incident_signature_ids,
        limit=10
    )
    
    logger.info(f"Retrieved {len(historical_resolutions)} historical resolutions")
    
    # Validate retrieval boundaries (guardrail: wrong retrieval)
    is_valid_retrieval, retrieval_errors = validate_resolution_retrieval_boundaries(
        retrieved_runbook_steps=runbook_steps,
        retrieved_historical_resolutions=historical_resolutions,
        expected_runbook_ids=runbook_ids,
        expected_incident_signature_ids=incident_signature_ids,
    )
    if not is_valid_retrieval:
        logger.error(f"Resolution retrieval boundary violation: {retrieval_errors}")
        raise ValueError(f"Resolution retrieval violated architecture boundaries: {', '.join(retrieval_errors)}")
    
    # 3. Get step success statistics
    step_ids = [step.get("step_id") for step in runbook_steps if step.get("step_id")]
    step_success_stats = get_step_success_stats(step_ids)
    
    logger.debug(f"Step success stats: {len(step_success_stats)} steps with history")
    
    # 4. Rank steps (algorithmic ranking)
    ranked_steps = rank_steps(
        steps=runbook_steps,
        incident_signature={
            "failure_type": incident_signature.failure_type,
            "error_class": incident_signature.error_class,
        },
        historical_resolutions=historical_resolutions,
        step_success_stats=step_success_stats,
    )
    
    logger.info(f"Ranked {len(ranked_steps)} steps")
    
    # 5. Assemble recommendations (algorithmic assembly)
    recommendations = assemble_recommendations(
        ranked_steps=ranked_steps,
        min_confidence=0.5,  # Configurable threshold
        max_steps=10,
    )
    
    if not recommendations:
        logger.warning("No recommendations assembled (all steps below confidence threshold)")
        return {
            "recommendations": [],
            "overall_confidence": 0.0,
            "risk_level": "high",
            "reasoning": "No steps met the minimum confidence threshold for recommendations.",
        }
    
    # 6. Use LLM to refine ordering and generate reasoning
    # Per architecture: LLM is used for final assembly/ordering, not for inventing steps
    llm_recommendations = _call_llm_for_ranking(
        triage_output=triage_output,
        runbook_steps=runbook_steps,
        historical_resolutions=historical_resolutions,
        ranked_recommendations=recommendations,
    )
    
    # Validate LLM ranking does not hallucinate (guardrail: hallucination)
    llm_recs = llm_recommendations.get("recommendations", [])
    is_valid_llm, llm_errors = validate_llm_ranking_no_hallucination(
        llm_recommendations=llm_recs,
        algorithmic_recommendations=recommendations,
    )
    if not is_valid_llm:
        logger.error(f"LLM ranking hallucination detected: {llm_errors}")
        # Fallback to algorithmic ranking if LLM hallucinates
        logger.warning("Falling back to algorithmic ranking due to LLM hallucination")
        final_recommendations = recommendations
    else:
        # Merge LLM output with algorithmic rankings
        # LLM can reorder but cannot add new steps
        final_recommendations = _merge_llm_ranking(
            algorithmic_recommendations=recommendations,
            llm_recommendations=llm_recs,
        )
    
    # Validate no step duplication (guardrail: step duplication)
    is_valid_no_dup, dup_errors = validate_no_step_duplication(final_recommendations)
    if not is_valid_no_dup:
        logger.error(f"Step duplication detected: {dup_errors}")
        # Remove duplicates by keeping first occurrence of each step_id
        seen_step_ids = set()
        deduplicated = []
        for rec in final_recommendations:
            step_id = rec.get("step_id")
            if step_id and step_id not in seen_step_ids:
                deduplicated.append(rec)
                seen_step_ids.add(step_id)
            elif not step_id:
                # Keep recommendations without step_id (shouldn't happen, but handle gracefully)
                deduplicated.append(rec)
        final_recommendations = deduplicated
        logger.warning(f"Removed duplicate steps. Final count: {len(final_recommendations)}")
    
    # Validate no hallucination in final recommendations (guardrail: hallucination)
    resolution_output_for_validation = {"recommendations": final_recommendations}
    is_valid_no_hallucination, hallucination_errors = validate_resolution_no_hallucination(
        resolution_output=resolution_output_for_validation,
        retrieved_runbook_steps=runbook_steps,
        retrieved_historical_resolutions=historical_resolutions,
    )
    if not is_valid_no_hallucination:
        logger.error(f"Resolution hallucination detected: {hallucination_errors}")
        raise ValueError(f"Resolution output contains hallucinated steps: {', '.join(hallucination_errors)}")
    
    # Calculate overall metrics
    overall_confidence = llm_recommendations.get(
        "overall_confidence",
        sum(r.get("confidence", 0.0) for r in final_recommendations) / len(final_recommendations) if final_recommendations else 0.0
    )
    
    risk_levels = [r.get("risk_level", "medium") for r in final_recommendations]
    risk_level = "high" if "high" in risk_levels else ("medium" if "medium" in risk_levels else "low")
    
    reasoning = llm_recommendations.get(
        "reasoning",
        f"Selected {len(final_recommendations)} steps from {len(runbook_steps)} available steps "
        f"based on relevance to {incident_signature.failure_type}/{incident_signature.error_class} "
        f"and historical success rates."
    )
    
    result = {
        "recommendations": final_recommendations,
        "overall_confidence": overall_confidence,
        "risk_level": risk_level,
        "reasoning": reasoning,
    }
    
    logger.info(
        f"Resolution agent completed: {len(final_recommendations)} recommendations, "
        f"confidence={overall_confidence:.2f}, risk={risk_level}"
    )
    
    return result


def _call_llm_for_ranking(
    triage_output: Dict[str, Any],
    runbook_steps: List[Dict],
    historical_resolutions: List[Dict],
    ranked_recommendations: List[Dict],
) -> Dict[str, Any]:
    """
    Call LLM to refine ranking and generate reasoning.
    
    Per architecture: LLM is used for final assembly, not for inventing steps.
    
    Args:
        triage_output: Triage output
        runbook_steps: Retrieved runbook steps
        historical_resolutions: Historical resolution records
        ranked_recommendations: Algorithmically ranked recommendations
        
    Returns:
        LLM output with recommendations and reasoning
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
            f"Rollback: {step.get('rollback', 'N/A')}\n"
        )
        runbook_steps_text.append(step_text)
    
    runbook_steps_text_str = "\n---\n\n".join(runbook_steps_text)
    
    # Format historical resolutions for prompt
    historical_resolutions_text = []
    for hist in historical_resolutions[:5]:  # Top 5
        hist_text = (
            f"Incident ID: {hist.get('incident_id')}\n"
            f"Successful: {hist.get('is_successful', False)}\n"
            f"Rollback Triggered: {hist.get('rollback_triggered', False)}\n"
            f"Resolution Steps: {hist.get('resolution_output', {}).get('steps', [])}\n"
        )
        historical_resolutions_text.append(hist_text)
    
    historical_resolutions_text_str = "\n---\n\n".join(historical_resolutions_text) if historical_resolutions_text else "No historical resolutions found."
    
    # Build prompt
    incident_sig = triage_output.get("incident_signature", {})
    matched_evidence = triage_output.get("matched_evidence", {})
    
    prompt = RESOLUTION_RANKING_PROMPT_TEMPLATE.format(
        failure_type=incident_sig.get("failure_type", "UNKNOWN"),
        error_class=incident_sig.get("error_class", "UNKNOWN"),
        incident_signature_ids=json.dumps(matched_evidence.get("incident_signatures", [])),
        runbook_ids=json.dumps(matched_evidence.get("runbook_refs", [])),
        severity=triage_output.get("severity", "medium"),
        confidence=triage_output.get("confidence", 0.5),
        runbook_steps_text=runbook_steps_text_str,
        historical_resolutions_text=historical_resolutions_text_str,
    )
    
    # Build request parameters
    request_params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    
    # Add response format if json_object
    if response_format_type == "json_object":
        request_params["response_format"] = {"type": "json_object"}
    
    # Add max_tokens if specified
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


def _merge_llm_ranking(
    algorithmic_recommendations: List[Dict],
    llm_recommendations: List[Dict],
) -> List[Dict]:
    """
    Merge LLM ranking with algorithmic ranking.
    
    Per architecture: LLM can reorder but cannot add new steps.
    Only steps from algorithmic_recommendations are included.
    
    Args:
        algorithmic_recommendations: Algorithmically ranked recommendations
        llm_recommendations: LLM-ranked recommendations
        
    Returns:
        Merged recommendations preserving provenance
    """
    # Create lookup by step_id
    algo_lookup = {r["step_id"]: r for r in algorithmic_recommendations if r.get("step_id")}
    
    # Use LLM ordering if provided, otherwise use algorithmic ordering
    if llm_recommendations:
        # Validate: all LLM recommendations must have step_ids from algorithmic recommendations
        final_recommendations = []
        seen_step_ids = set()
        
        for llm_rec in llm_recommendations:
            step_id = llm_rec.get("step_id")
            if step_id and step_id in algo_lookup:
                if step_id not in seen_step_ids:
                    # Use LLM confidence if provided, otherwise use algorithmic
                    merged = algo_lookup[step_id].copy()
                    if "confidence" in llm_rec:
                        merged["confidence"] = llm_rec["confidence"]
                    if "reasoning" in llm_rec:
                        merged["llm_reasoning"] = llm_rec.get("reasoning", "")
                    final_recommendations.append(merged)
                    seen_step_ids.add(step_id)
            else:
                logger.warning(
                    f"LLM recommendation has invalid step_id: {step_id}. "
                    "Skipping (per architecture: cannot add new steps)."
                )
        
        # Add any algorithmic recommendations not in LLM output
        for step_id, algo_rec in algo_lookup.items():
            if step_id not in seen_step_ids:
                final_recommendations.append(algo_rec)
        
        return final_recommendations
    else:
        # No LLM output, use algorithmic ranking
        return algorithmic_recommendations

