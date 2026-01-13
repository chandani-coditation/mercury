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
import json
from pathlib import Path
from ai_service.core import get_logger, get_llm_config
from ai_service.models import TriageOutput
from ai_service.repositories import IncidentRepository
from ai_service.core import IncidentNotFoundError

# Load problem keywords config
_PROBLEM_KEYWORDS_CONFIG = None


def _load_problem_keywords_config():
    """Load problem keywords configuration from config file."""
    global _PROBLEM_KEYWORDS_CONFIG
    if _PROBLEM_KEYWORDS_CONFIG is None:
        try:
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "problem_keywords.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    _PROBLEM_KEYWORDS_CONFIG = json.load(f)
            else:
                _PROBLEM_KEYWORDS_CONFIG = {}
                logger = get_logger(__name__)
                logger.warning("problem_keywords.json not found, using defaults")
        except Exception as e:
            logger = get_logger(__name__)
            logger.warning(f"Failed to load problem_keywords.json: {e}")
            _PROBLEM_KEYWORDS_CONFIG = {}
    return _PROBLEM_KEYWORDS_CONFIG


def _get_corrective_action_keywords():
    """Get corrective action keywords from config."""
    config = _load_problem_keywords_config()
    return config.get("corrective_action_keywords", {}).get(
        "keywords", ["reduce", "clean", "fix", "resolve", "remove", "clear", "free", "backup"]
    )


def _get_preferred_step_types():
    """Get preferred step types for filtering from config."""
    config = _load_problem_keywords_config()
    return config.get("step_type_filters", {}).get("preferred_types", ["mitigation", "resolution"])


def _get_problem_keyword_groups():
    """Get problem keyword groups from config."""
    config = _load_problem_keywords_config()
    return config.get("problem_keyword_groups", {})


from retrieval.resolution_retrieval import (
    retrieve_runbook_chunks_by_document_id,
    retrieve_historical_resolutions,
    retrieve_close_notes_from_signatures,
    get_step_success_stats,
)
from ai_service.ranking import rank_steps
from ai_service.llm_client import get_llm_client, _call_llm_with_retry
from ai_service.core import get_llm_handler
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

    # 1. Retrieve runbook steps
    if not runbook_ids:
        logger.warning("No runbook_ids in triage output matched_evidence.runbook_refs")
        # Try to get runbook_ids from evidence if available
        if isinstance(triage_output, dict):
            evidence = triage_output.get("evidence") or {}
            runbook_metadata = evidence.get("runbook_metadata", [])
            if runbook_metadata:
                runbook_ids = [
                    rb.get("runbook_id") for rb in runbook_metadata if rb.get("runbook_id")
                ]
                logger.info(f"Extracted runbook_ids from evidence: {runbook_ids}")
            else:
                logger.warning("No runbook_metadata found in evidence")

    # Retrieve runbook steps using document_id from triage (preferred method)
    # IMPORTANT: Use only the TOP runbook (highest score) from triage to ensure steps are from a single runbook
    evidence = triage_output.get("evidence", {})
    runbook_metadata = evidence.get("runbook_metadata", [])

    # Select the top runbook based on highest combined score (relevance_score + service_match_boost + component_match_boost)
    # This ensures we use the best match from triage, not just the first one
    if runbook_metadata:
        # Calculate combined score for each runbook and sort by it
        for rb in runbook_metadata:
            relevance_score = float(rb.get("relevance_score", 0.0))
            service_boost = float(rb.get("service_match_boost", 0.0))
            component_boost = float(rb.get("component_match_boost", 0.0))
            rb["combined_score"] = relevance_score + service_boost + component_boost
            logger.debug(
                f"Runbook '{rb.get('title', 'Unknown')}': "
                f"relevance={relevance_score:.3f}, service_boost={service_boost:.3f}, "
                f"component_boost={component_boost:.3f}, combined={rb['combined_score']:.3f}"
            )

        # Sort by combined score (descending) to get the highest scoring runbook first
        runbook_metadata = sorted(
            runbook_metadata, key=lambda x: x.get("combined_score", 0.0), reverse=True
        )
        logger.info(
            f"Sorted {len(runbook_metadata)} runbooks by score. Top runbook: "
            f"{runbook_metadata[0].get('title', 'Unknown')} "
            f"(score: {runbook_metadata[0].get('combined_score', 0.0):.3f})"
        )

    top_runbook = runbook_metadata[0] if runbook_metadata else None
    if not top_runbook:
        logger.warning("No runbook_metadata found in evidence")
        runbook_steps = []
    else:
        top_document_id = top_runbook.get("document_id")
        if not top_document_id:
            logger.warning(f"Top runbook has no document_id: {top_runbook}")
            runbook_steps = []
        else:
            # Use only the top runbook's document_id
            logger.info(
                f"Using single runbook: {top_runbook.get('title', 'Unknown')} (document_id: {top_document_id})"
            )

            # Build query text from triage signals for semantic search
            query_text_parts = []
            if incident_signature.failure_type:
                query_text_parts.append(incident_signature.failure_type)
            if incident_signature.error_class:
                query_text_parts.append(incident_signature.error_class)
            summary = triage_output.get("summary", "")
            if summary:
                query_text_parts.append(summary[:200])  # Limit length
            query_text = " ".join(query_text_parts) if query_text_parts else None

            # Retrieve steps from only the top runbook
            runbook_steps = retrieve_runbook_chunks_by_document_id(
                document_ids=[top_document_id],  # Single document_id only
                query_text=query_text,
                limit=20,
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

    # Store original count before filtering (for evidence reporting)
    original_runbook_steps_count = len(runbook_steps)

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
    # 2.5. Identify root problem from triage output (generic, not hard-coded)
    root_problem = _identify_root_problem(triage_output, incident_signature)
    logger.info(f"Identified root problem: {root_problem}")

    # 2.6. Match remediation steps to root problem (generic matching)
    # Filter steps where condition matches the root problem
    matched_remediation_steps = _match_remediation_to_problem(filtered_steps, root_problem)
    if matched_remediation_steps:
        logger.info(f"Matched {len(matched_remediation_steps)} remediation steps to root problem")
        # Prioritize matched remediation steps
        filtered_steps = matched_remediation_steps + [
            s for s in filtered_steps if s not in matched_remediation_steps
        ]

    # 2.5. Identify root problem from triage output (generic, not hard-coded)
    root_problem = _identify_root_problem(triage_output, incident_signature)
    logger.info(f"Identified root problem: {root_problem}")

    # 2.6. Match remediation steps to root problem (generic matching)
    # Filter steps where condition matches the root problem
    matched_remediation_steps = _match_remediation_to_problem(filtered_steps, root_problem)
    if matched_remediation_steps:
        logger.info(f"Matched {len(matched_remediation_steps)} remediation steps to root problem")
        # Prioritize matched remediation steps
        filtered_steps = matched_remediation_steps + [
            s for s in filtered_steps if s not in matched_remediation_steps
        ]

    # 3. Retrieve historical resolutions and close notes for context
    historical_resolutions = retrieve_historical_resolutions(incident_signature_ids, limit=10)

    close_notes_list = retrieve_close_notes_from_signatures(incident_signature_ids, limit=10)

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

    # 6.5. Ensure we have mitigation and/or resolution steps (CRITICAL)
    # If we only have investigation/verification, boost relevance for disk/IO/log/tempdb steps
    step_types_present = {step.get("_inferred_step_type") for step in ordered_steps}
    has_mitigation_or_resolution = (
        "mitigation" in step_types_present or "resolution" in step_types_present
    )

    if not has_mitigation_or_resolution:
        logger.warning(
            "No mitigation or resolution steps found. Boosting relevance for corrective actions."
        )
        # Re-rank with higher weight for disk/IO/log/tempdb related steps
        triage_summary = triage_output.get("summary", "").lower()
        triage_likely_cause = triage_output.get("likely_cause", "").lower()
        triage_text = f"{triage_summary} {triage_likely_cause}"

        # Boost steps that mention disk/IO/log/tempdb/space
        relevance_keywords = [
            "disk",
            "io",
            "i/o",
            "log",
            "tempdb",
            "space",
            "usage",
            "volume",
            "file",
            "backup",
        ]
        for step in ordered_steps:
            action = (step.get("action", "") or "").lower()
            condition = (step.get("condition", "") or "").lower()
            step_text = f"{action} {condition}"

            # Boost relevance if step mentions problem keywords
            if any(keyword in step_text for keyword in relevance_keywords):
                # Also check if it's a corrective action (not just investigation)
                corrective_keywords = _get_corrective_action_keywords()
                if any(word in step_text for word in corrective_keywords):
                    # Boost this step significantly
                    current_score = step.get("combined_score", 0.0)
                    step["combined_score"] = min(1.0, current_score + 0.3)

        # Re-order after boosting
        ordered_steps = sorted(
            ordered_steps, key=lambda s: s.get("combined_score", 0.0), reverse=True
        )

    # 7. Limit to top 4-6 steps for UI (prefer fewer, more focused steps)
    max_steps = 6
    selected_steps = ordered_steps[:max_steps]

    # 7.5. Ensure at least one mitigation or resolution step is included
    preferred_types = _get_preferred_step_types()
    selected_types = {step.get("_inferred_step_type") for step in selected_steps}
    if not any(step_type in selected_types for step_type in preferred_types):
        # Find the best preferred step type and add it
        for step in ordered_steps:
            step_type = step.get("_inferred_step_type")
            if step_type in preferred_types:
                if step not in selected_steps:
                    selected_steps.append(step)
                    logger.info(
                        f"Added {step_type} step to ensure corrective action: {step.get('step_id')}"
                    )
                    break

    logger.info(f"Selected {len(selected_steps)} steps for resolution plan")

    # 8. Transform steps for UI format (with titles, clean actions)
    ui_steps = []
    for idx, step in enumerate(selected_steps, 1):
        ui_step = transform_step_for_ui(step, idx)
        ui_steps.append(ui_step)

    # 9. LLM enhancement disabled - Pure RAG mode
    # All steps come directly from runbook chunks (RAG retrieval only)
    # No LLM generation or enhancement is used
    logger.debug("RAG-only mode: Using runbook steps directly without LLM enhancement")

    final_steps = ui_steps

    # 10. Calculate overall metrics
    # Base confidence from triage output (if available)
    triage_confidence = triage_output.get("confidence", 0.0)

    # Calculate step-level confidence average
    step_confidences = [
        s.get("confidence", 0.0) for s in final_steps if s.get("confidence", 0.0) > 0
    ]
    avg_step_confidence = sum(step_confidences) / len(step_confidences) if step_confidences else 0.0

    # Combine triage confidence (40%) with step confidence (60%)
    # This ensures resolution confidence reflects both triage quality and step relevance
    if triage_confidence > 0 and avg_step_confidence > 0:
        overall_confidence = (triage_confidence * 0.4) + (avg_step_confidence * 0.6)
    elif triage_confidence > 0:
        # If no step confidence, use triage confidence but reduce it
        overall_confidence = triage_confidence * 0.7
    elif avg_step_confidence > 0:
        # If no triage confidence, use step confidence
        overall_confidence = avg_step_confidence
    else:
        # Fallback: base confidence on runbook match quality
        if runbook_steps and len(runbook_steps) > 0:
            overall_confidence = 0.6  # Moderate confidence if we have runbook steps
        else:
            overall_confidence = 0.0

    # Ensure confidence is reasonable (not too low if we have good evidence)
    if len(final_steps) > 0 and runbook_steps and len(runbook_steps) > 0:
        # Boost confidence if we have matched runbook steps
        if overall_confidence < 0.5:
            overall_confidence = min(0.75, overall_confidence + 0.25)

        # Additional boost if triage confidence is high (indicates good evidence match)
        if triage_confidence >= 0.8:
            # High triage confidence means good evidence match, so resolution should reflect that
            overall_confidence = max(overall_confidence, triage_confidence * 0.75)

        # Boost confidence if multiple steps were generated (indicates good match)
        if len(final_steps) >= 3:
            overall_confidence = min(0.85, overall_confidence + 0.1)

    # Note: risk_level and estimated_time calculations removed - these fields are deprecated
    # They are set to None in the output for backward compatibility

    # 12. Build reasoning from triage signals
    summary = triage_output.get("summary", "")
    likely_cause = triage_output.get("likely_cause", "")
    failure_type = incident_signature.failure_type
    error_class = incident_signature.error_class

    # Build context-aware reasoning - emphasize runbooks as primary source
    # Check what types of steps we have
    step_types = [step.get("_inferred_step_type") for step in selected_steps]
    has_mitigation = "mitigation" in step_types
    has_resolution = "resolution" in step_types

    if has_mitigation or has_resolution:
        action_type = (
            "mitigation and resolution"
            if (has_mitigation and has_resolution)
            else ("mitigation" if has_mitigation else "resolution")
        )
        if summary and likely_cause:
            reasoning = f"{summary}. {likely_cause}. Steps are based on runbook procedures and focus on {action_type} to address {failure_type} and {error_class}."
        elif likely_cause:
            reasoning = f"{likely_cause}. Steps are based on runbook procedures and focus on {action_type} to resolve {failure_type}/{error_class}."
        else:
            reasoning = f"Steps are selected from runbook procedures for {action_type} of {failure_type}/{error_class}."
    else:
        # Fallback if somehow we don't have mitigation/resolution
        if summary and likely_cause:
            reasoning = f"{summary}. {likely_cause}. Steps are based on runbook procedures to address {failure_type} and {error_class}."
        elif likely_cause:
            reasoning = f"{likely_cause}. Steps are based on runbook procedures to resolve {failure_type}/{error_class}."
        else:
            reasoning = f"Steps are selected from runbook procedures based on relevance to {failure_type}/{error_class}."

    # Ensure reasoning mentions runbooks (critical for user understanding)
    if "runbook" not in reasoning.lower():
        # Prepend runbook mention if missing
        if reasoning.startswith("Steps"):
            reasoning = "Steps from runbook procedures: " + reasoning[6:].lower()
        else:
            reasoning = "Based on runbook procedures: " + reasoning

    # Ensure reasoning is concise but preserve runbook mention
    if len(reasoning) > 300:
        # Try to preserve "runbook" in the truncated version
        if "runbook" in reasoning[:250].lower():
            reasoning = reasoning[:297] + "..."
        else:
            # If runbook is near the end, truncate more carefully
            runbook_pos = reasoning.lower().find("runbook")
            if runbook_pos > 0 and runbook_pos < 250:
                reasoning = reasoning[:297] + "..."
            else:
                # Force include runbook mention
                reasoning = reasoning[:270] + "... (from runbook procedures)"

    # 13. Build final output in new format
    # Note: risk_level and estimated_time_minutes are deprecated and set to None
    # step.risk_level is also deprecated but kept for backward compatibility (set to None)
    result = {
        "steps": [
            {
                "step_number": step.get("step_number"),
                "title": step.get("title"),
                "action": step.get("action"),
                "expected_outcome": step.get("expected_outcome"),
                # risk_level deprecated - not based on historical data, set to None
                "risk_level": None,
            }
            for step in final_steps
        ],
        # estimated_time_minutes removed - not reliable, set to None
        "estimated_time_minutes": None,
        # risk_level deprecated - not based on historical data, set to None
        "risk_level": None,
        "confidence": overall_confidence,
        "reasoning": reasoning,
        # Include metadata about runbook usage (for API response)
        "_metadata": {
            "runbook_steps_retrieved": original_runbook_steps_count,
            "runbook_steps_after_filtering": len(filtered_steps),
            "runbook_steps_final": len(final_steps),
        },
    }

    logger.info(
        f"Resolution agent completed: {len(final_steps)} steps from {original_runbook_steps_count} runbook steps, "
        f"confidence={overall_confidence:.2f}"
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
    handler = get_llm_handler()

    # Get LLM config
    llm_config = get_llm_config()
    resolution_config = llm_config.get("resolution", {})

    model = resolution_config.get("model", "gpt-4-turbo-preview")
    temperature = resolution_config.get("temperature", 0.2)
    system_prompt = resolution_config.get("system_prompt", RESOLUTION_RANKING_SYSTEM_PROMPT_DEFAULT)
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
    historical_resolutions_text_str = (
        "\n".join(historical_resolutions_text) if historical_resolutions_text else "None"
    )

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
        response = _call_llm_with_retry(handler, request_params, "resolution_ranking", model)

        result_text = response.choices[0].message.content
        result = json.loads(result_text)

        return result

    except Exception as e:
        logger.error(f"LLM ranking failed: {str(e)}", exc_info=True)
        # Fallback to algorithmic ranking
        return {
            "recommendations": ranked_recommendations,
            "overall_confidence": (
                sum(r.get("confidence", 0.0) for r in ranked_recommendations)
                / len(ranked_recommendations)
                if ranked_recommendations
                else 0.0
            ),
            "reasoning": "Ranking completed using algorithmic scoring (LLM ranking unavailable).",
        }


def _identify_root_problem(triage_output: Dict[str, Any], incident_signature: Any) -> str:
    """
    Identify root problem from triage output (generic, not hard-coded).

    Uses failure_type, error_class, summary, and likely_cause to identify the problem.
    Returns a problem description that can be matched against runbook step conditions.
    """
    problem_parts = []

    # Use failure_type and error_class as primary signals
    if incident_signature.failure_type:
        problem_parts.append(incident_signature.failure_type)
    if incident_signature.error_class:
        problem_parts.append(incident_signature.error_class)

    # Use likely_cause if available
    likely_cause = triage_output.get("likely_cause", "")
    if likely_cause and len(likely_cause) > 10:
        # Extract key problem terms from likely_cause
        problem_parts.append(likely_cause[:100])

    # Use summary for additional context
    summary = triage_output.get("summary", "")
    if summary:
        # Extract key problem indicators from summary using config-driven keyword groups
        summary_lower = summary.lower()
        problem_keywords = []
        keyword_groups = _get_problem_keyword_groups()

        # Check each keyword group from config
        # Skip metadata keys (starting with _) and ensure group_config is a dict
        for group_name, group_config in keyword_groups.items():
            # Skip metadata fields (keys starting with _)
            if group_name.startswith("_"):
                continue
            # Safety check: ensure group_config is a dictionary
            if not isinstance(group_config, dict):
                logger.warning(
                    f"Invalid group_config type for '{group_name}': expected dict, got {type(group_config)}"
                )
                continue
            keywords = group_config.get("keywords", [])
            problem_type = group_config.get("problem_type", group_name)
            if any(word in summary_lower for word in keywords):
                problem_keywords.append(problem_type)

        if problem_keywords:
            problem_parts.extend(problem_keywords)

    # Combine into a problem description
    root_problem = " ".join(problem_parts).lower()
    return root_problem


def _match_remediation_to_problem(steps: List[Dict], root_problem: str) -> List[Dict]:
    """
    Match remediation steps to root problem (generic matching).

    Matches steps where the condition field contains keywords from root_problem.
    Returns matched steps in order of relevance.
    """
    if not root_problem or not steps:
        return []

    matched_steps = []
    root_problem_lower = root_problem.lower()

    # Extract key problem terms
    problem_terms = set(root_problem_lower.split())
    # Remove common stop words
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "is",
        "are",
        "was",
        "were",
    }
    problem_terms = {term for term in problem_terms if term not in stop_words and len(term) > 2}

    for step in steps:
        condition = (step.get("condition") or "").lower()
        action = (step.get("action") or "").lower()

        # Check if condition matches problem terms
        condition_matches = sum(1 for term in problem_terms if term in condition)
        action_matches = sum(1 for term in problem_terms if term in action)

        # Score based on matches
        match_score = condition_matches * 2 + action_matches  # Condition matches are more important

        if match_score > 0:
            step["_remediation_match_score"] = match_score
            matched_steps.append(step)

    # Sort by match score (highest first)
    matched_steps.sort(key=lambda s: s.get("_remediation_match_score", 0), reverse=True)

    return matched_steps
