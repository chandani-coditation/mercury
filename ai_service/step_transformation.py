"""Step transformation and classification for Resolution Agent.

This module handles:
- Step type classification (investigation, mitigation, resolution, verification, etc.)
- Step filtering (remove documentation/context steps)
- Step ordering by logical flow
- Step transformation (generate titles, clean actions)
"""

from typing import List, Dict, Optional
import re
import json
from pathlib import Path
from ai_service.core import get_logger

logger = get_logger(__name__)

# Load step classification config
_STEP_CLASSIFICATION_CONFIG = None


def _load_step_classification_config():
    """Load step classification configuration from config file."""
    global _STEP_CLASSIFICATION_CONFIG
    if _STEP_CLASSIFICATION_CONFIG is None:
        try:
            # Path resolution: __file__ is in ai_service/, so parent.parent is project root
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "step_classification.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    _STEP_CLASSIFICATION_CONFIG = json.load(f)
                logger.debug(f"Loaded step_classification.json from {config_path}")
            else:
                _STEP_CLASSIFICATION_CONFIG = {}
                logger.warning(f"step_classification.json not found at {config_path}, using defaults")
        except Exception as e:
            logger.warning(f"Failed to load step_classification.json: {e}")
            _STEP_CLASSIFICATION_CONFIG = {}
    return _STEP_CLASSIFICATION_CONFIG


def _get_step_type_priority_order():
    """Get step type priority order from config."""
    config = _load_step_classification_config()
    return config.get("step_types", {}).get(
        "priority_order", ["investigation", "mitigation", "resolution", "verification", "rollback"]
    )


def _get_filtered_step_types():
    """Get step types that should be filtered out."""
    config = _load_step_classification_config()
    return (
        config.get("step_types", {})
        .get("filtered_types", {})
        .get("types", ["documentation", "context"])
    )


def _get_documentation_phrases():
    """Get documentation phrases from config."""
    config = _load_step_classification_config()
    return config.get("documentation_phrases", {}).get("phrases", [])


def _get_actionable_indicators():
    """Get actionable indicators from config."""
    config = _load_step_classification_config()
    return config.get("actionable_indicators", {}).get("indicators", [])


def _get_step_type_keywords(step_type: str):
    """Get keywords for a specific step type from config."""
    config = _load_step_classification_config()
    return config.get("step_type_keywords", {}).get(step_type, [])


def _get_risk_level_keywords():
    """Get risk level keywords from config."""
    config = _load_step_classification_config()
    risk_levels = config.get("risk_levels", {})
    return {
        "valid_levels": risk_levels.get("valid_levels", ["low", "medium", "high", "critical"]),
        "default_level": risk_levels.get("default_level", "medium"),
        "high_risk": risk_levels.get("high_risk_keywords", {}).get(
            "keywords", ["kill", "delete", "drop", "remove", "stop", "restart"]
        ),
        "medium_risk": risk_levels.get("medium_risk_keywords", {}).get(
            "keywords", ["update", "modify", "change", "alter"]
        ),
    }


def classify_step_type(step: Dict) -> str:
    """
    Classify a runbook step by analyzing its action text.

    Args:
        step: Step dictionary with 'action' field

    Returns:
        Step type: 'investigation', 'mitigation', 'resolution', 'verification',
                   'documentation', 'context', or 'unknown'
    """
    action = (step.get("action") or "").lower()
    condition = (step.get("condition") or "").lower()
    combined = f"{action} {condition}".lower()

    # Documentation/Context steps (should be filtered out) - AGGRESSIVE FILTERING
    # Check for documentation/impact assessment patterns FIRST (before other classifications)
    action_lower = action.lower()
    condition_lower = condition.lower()

    # Hard filter: If action is primarily about documenting/recording/impact assessment
    # BUT: Allow if step contains actionable content (like "Action:", "Restart", "Fix", etc.)
    doc_phrases = _get_documentation_phrases()

    # Check if action contains documentation/impact phrases
    if any(phrase in action_lower for phrase in doc_phrases):
        # Check if step also contains actionable content - if yes, don't filter as documentation
        actionable_indicators = _get_actionable_indicators()
        # If it contains actionable content, don't filter as documentation
        if not any(indicator in action_lower for indicator in actionable_indicators):
            return "documentation"

    # Check if action starts with document/record/log/note and is ONLY about that
    # BUT: Allow if it contains actionable content (like "Actions taken", "Restart", etc.)
    if action_lower.startswith(("document", "record", "log", "note", "track")):
        # Check for actionable content - if present, don't filter as documentation
        actionable_indicators = _get_actionable_indicators()
        # If it contains actionable content, don't filter as documentation
        if any(indicator in action_lower for indicator in actionable_indicators):
            # Continue to classification (don't return "documentation")
            pass
        else:
            # Only documenting, no actionable content
            return "documentation"

    # Also check if action contains "record all actions" or "document all actions" - these are always documentation
    if "record all actions" in action_lower or "document all actions" in action_lower:
        return "documentation"

    # Check if action is about recording/documenting actions taken (past tense indicates documentation)
    # BUT: Allow if step contains actionable content (like "Action:", "Restart", "Fix", etc.)
    documentation_phrases = _get_documentation_phrases()
    if any(phrase in action_lower for phrase in documentation_phrases):
        # Check if step also contains actionable content - if yes, don't filter as documentation
        actionable_indicators = _get_actionable_indicators()
        # If it contains actionable content, don't filter as documentation
        if not any(indicator in action_lower for indicator in actionable_indicators):
            return "documentation"

    # Check for "assess impact" or "impact assessment" patterns
    # BUT: Allow if step contains actionable content (like "Action:", "Restart", "Fix", etc.)
    if (
        "assess impact" in action_lower
        or "impact assessment" in action_lower
        or "evaluate impact" in action_lower
    ):
        # Check if step also contains actionable content - if yes, don't filter as documentation
        actionable_indicators = _get_actionable_indicators()
        # If it contains actionable content, don't filter as documentation
        if not any(indicator in action_lower for indicator in actionable_indicators):
            return "documentation"

    # Check for "follow-up" patterns that are just administrative
    # BUT: Allow if step contains actionable content (like "Action:", "Restart", "Fix", etc.)
    if "follow-up" in action_lower or "follow up" in action_lower:
        if "identify" in action_lower or "assess" in action_lower:
            # Check if step also contains actionable content - if yes, don't filter as documentation
            actionable_indicators = _get_actionable_indicators()
            # If it contains actionable content, don't filter as documentation
            if not any(indicator in action_lower for indicator in actionable_indicators):
                return "documentation"

    # Investigation steps
    investigation_keywords = _get_step_type_keywords("investigation")
    if any(keyword in combined for keyword in investigation_keywords):
        return "investigation"

    # Mitigation steps (quick relief) - PRIORITIZE THESE
    mitigation_keywords = _get_step_type_keywords("mitigation")
    if any(keyword in combined for keyword in mitigation_keywords):
        return "mitigation"

    # Resolution steps (root fix) - PRIORITIZE THESE
    resolution_keywords = _get_step_type_keywords("resolution")
    if any(keyword in combined for keyword in resolution_keywords):
        return "resolution"

    # Verification steps
    verification_keywords = _get_step_type_keywords("verification")
    if any(keyword in combined for keyword in verification_keywords):
        return "verification"

    # Rollback steps
    rollback_keywords = _get_step_type_keywords("rollback")
    if any(keyword in combined for keyword in rollback_keywords):
        return "rollback"

    # Default: classify as investigation if unclear
    return "investigation"


def filter_steps(steps: List[Dict]) -> List[Dict]:
    """
    Filter out documentation and context steps.

    Args:
        steps: List of step dictionaries

    Returns:
        Filtered list with documentation/context steps removed
    """
    filtered = []
    filtered_types = _get_filtered_step_types()
    for step in steps:
        step_type = classify_step_type(step)
        action_preview = (step.get("action") or "")[:100]  # First 100 chars for logging
        if step_type not in filtered_types:
            step["_inferred_step_type"] = step_type
            filtered.append(step)
        else:
            logger.warning(
                f"Filtered out {step_type} step (step_id: {step.get('step_id', 'unknown')}): "
                f"{action_preview}..."
            )

    logger.info(f"Filtered {len(steps)} steps to {len(filtered)} actionable steps")
    if len(filtered) == 0 and len(steps) > 0:
        # Log details about why all steps were filtered
        logger.warning(f"All {len(steps)} steps were filtered. Sample step actions:")
        for i, step in enumerate(steps[:3], 1):  # Show first 3 steps
            action = step.get("action", "")[:200]
            step_type = classify_step_type(step)
            logger.warning(f"  Step {i} (type: {step_type}): {action}...")
    return filtered


def order_steps_by_type(steps: List[Dict]) -> List[Dict]:
    """
    Order steps by logical flow: investigation → mitigation → resolution → verification.

    Within each type, order by relevance score if available.

    Args:
        steps: List of step dictionaries with '_inferred_step_type'

    Returns:
        Ordered list of steps
    """
    # Group by type
    by_type = {}
    for step in steps:
        step_type = step.get("_inferred_step_type", "unknown")
        if step_type not in by_type:
            by_type[step_type] = []
        by_type[step_type].append(step)

    # Sort each group by relevance (if available) or confidence
    for step_type, group in by_type.items():
        group.sort(
            key=lambda s: (
                s.get("similarity_score", 0),
                s.get("combined_score", 0),
                s.get("confidence", 0),
            ),
            reverse=True,
        )

    # Order by type priority (from config)
    ordered = []
    step_type_order = _get_step_type_priority_order()
    for step_type in step_type_order:
        if step_type in by_type:
            ordered.extend(by_type[step_type])

    # Add any unknown types at the end
    if "unknown" in by_type:
        ordered.extend(by_type["unknown"])

    logger.info(f"Ordered {len(ordered)} steps by type")
    return ordered


def generate_step_title(action: str, step_type: str) -> str:
    """
    Generate a short, UI-friendly title from action text.
    
    Title should be concise (max 80 chars) to save space in UI.
    Full action text is shown separately in the action field.

    Args:
        action: Action text
        step_type: Inferred step type

    Returns:
        Short title (max 80 characters, typically 3-8 words)
    """
    if not action:
        return "Execute step"

    # FIRST: Try to extract the actual action (after "Action:" marker) instead of prerequisites
    # Many runbook steps have format: "Prerequisites: ... Action: <actual action>"
    # Handle both "Action:" and "\nAction:" formats
    action_marker = "Action:"
    if action_marker in action:
        # Split on action marker (handles both "Action:" and "\nAction:")
        parts = action.split(action_marker, 1)
        if len(parts) > 1:
            action_part = parts[1].strip()
            # Remove any trailing service/component info
            if "\nService:" in action_part:
                action_part = action_part.split("\nService:")[0].strip()
            if action_part:
                # Truncate to first sentence or 80 chars for title
                # Extract first sentence (up to period, comma, or newline)
                first_sentence = action_part.split('.')[0].split(',')[0].split('\n')[0].strip()
                if len(first_sentence) <= 80:
                    title = first_sentence
                else:
                    # Truncate to 80 chars at word boundary
                    truncated = action_part[:77]
                    last_space = truncated.rfind(' ')
                    if last_space > 50:  # Only truncate at word if reasonable
                        title = truncated[:last_space] + "..."
                    else:
                        title = truncated + "..."
                # Capitalize first letter
                title = title[0].upper() + title[1:] if title else title
                return title

    # Remove common prefixes
    action_clean = action.strip()
    prefixes = [
        "when",
        "if",
        "step",
        "action:",
        "condition:",
        "record",
        "document",
        "check",
        "verify",
    ]
    for prefix in prefixes:
        if action_clean.lower().startswith(prefix):
            action_clean = action_clean[len(prefix) :].strip()
            if action_clean.startswith(":"):
                action_clean = action_clean[1:].strip()
    
    # Extract key phrases - look for imperative verbs at the start
    # Limit to first sentence or 80 chars for title
    imperative_patterns = [
        r"^(check|verify|review|examine|analyze|identify|fix|resolve|repair|restore|reduce|decrease|clean|monitor|confirm|validate)\s+([^.]+)",
        r"^([A-Z][^.]+)",  # Capitalized sentence start
    ]

    for pattern in imperative_patterns:
        match = re.match(pattern, action_clean, re.IGNORECASE)
        if match:
            title = match.group(1 if len(match.groups()) == 1 else 2)
            # Clean up title
            title = title.strip()
            # Extract first sentence or truncate to 80 chars
            first_sentence = title.split('.')[0].split(',')[0].split('\n')[0].strip()
            if len(first_sentence) <= 80:
                title = first_sentence
            else:
                truncated = title[:77]
                last_space = truncated.rfind(' ')
                if last_space > 50:
                    title = truncated[:last_space] + "..."
                else:
                    title = truncated + "..."
            # Capitalize first letter
            title = title[0].upper() + title[1:] if title else title
            return title

    # Fallback: use first sentence or truncate to 80 chars
    title = action_clean.strip()
    first_sentence = title.split('.')[0].split(',')[0].split('\n')[0].strip()
    if len(first_sentence) <= 80:
        return first_sentence
    else:
        truncated = title[:77]
        last_space = truncated.rfind(' ')
        if last_space > 50:
            return truncated[:last_space] + "..."
        else:
            return truncated + "..."


def clean_action_for_ui(action: str) -> str:
    """
    Clean action text to be UI-ready: remove SQL, commands, make it plain English.

    Args:
        action: Raw action text

    Returns:
        Cleaned, plain English action
    """
    if not action:
        return action

    # Remove SQL queries
    lines = action.split("\n")
    cleaned_lines = []
    for line in lines:
        line_stripped = line.strip()
        # Skip SQL statements
        if re.match(
            r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXEC|EXECUTE|USE|DECLARE)\s+",
            line_stripped,
            re.IGNORECASE,
        ):
            continue
        # Skip command-line commands
        if re.match(
            r"^\s*[$#]|^\s*(sudo|systemctl|kubectl|docker|psql|mysql)", line_stripped, re.IGNORECASE
        ):
            continue
        # Skip code blocks
        if line_stripped.startswith("```") or line_stripped.endswith("```"):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()

    # Remove inline SQL patterns
    cleaned = re.sub(
        r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXEC|EXECUTE|USE|DECLARE)\s+[^.]*\.",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)  # Remove code blocks
    cleaned = re.sub(r"\$[^\s]+", "", cleaned)  # Remove command-line patterns

    # Remove generic prefixes
    cleaned = re.sub(
        r"^(step\s+\d+\s*:?\s*|action:\s*|condition:\s*)", "", cleaned, flags=re.IGNORECASE
    )

    return cleaned.strip()


def transform_step_for_ui(step: Dict, step_number: int) -> Dict:
    """
    Transform a runbook step into UI-ready format.

    Args:
        step: Step dictionary with action, condition, etc.
        step_number: Step number in the ordered sequence

    Returns:
        Transformed step with step_number, title, action, expected_outcome, risk_level
    """
    action = step.get("action", "")
    step_type = step.get("_inferred_step_type", "investigation")

    # Clean action
    cleaned_action = clean_action_for_ui(action)

    # Generate title
    title = generate_step_title(cleaned_action, step_type)

    # Get expected outcome
    expected_outcome = step.get("expected_outcome")
    if not expected_outcome:
        # Generate from action
        if "check" in cleaned_action.lower() or "verify" in cleaned_action.lower():
            expected_outcome = "Issue identified and understood"
        elif "fix" in cleaned_action.lower() or "resolve" in cleaned_action.lower():
            expected_outcome = "Issue resolved"
        elif "reduce" in cleaned_action.lower() or "decrease" in cleaned_action.lower():
            expected_outcome = "Issue severity reduced"
        elif "monitor" in cleaned_action.lower():
            expected_outcome = "System stability confirmed"
        else:
            expected_outcome = "Step completed successfully"

    # Get risk level
    risk_config = _get_risk_level_keywords()
    valid_levels = risk_config["valid_levels"]
    default_level = risk_config["default_level"]
    high_risk_keywords = risk_config["high_risk"]
    medium_risk_keywords = risk_config["medium_risk"]

    risk_level = step.get("risk_level", default_level)
    if not risk_level or risk_level.lower() not in valid_levels:
        # Infer from action
        action_lower = cleaned_action.lower()
        if any(word in action_lower for word in high_risk_keywords):
            risk_level = "high"
        elif any(word in action_lower for word in medium_risk_keywords):
            risk_level = "medium"
        else:
            risk_level = "low"

    return {
        "step_number": step_number,
        "title": title,
        "action": cleaned_action,
        "expected_outcome": expected_outcome,
        "risk_level": risk_level.lower(),
        "confidence": step.get("confidence", step.get("combined_score", 0.7)),
        "provenance": {
            "runbook_id": step.get("runbook_id"),
            "step_id": step.get("step_id"),
            "chunk_id": step.get("chunk_id"),
            "document_id": step.get("document_id"),
        },
    }


def calculate_estimated_time(steps: List[Dict]) -> int:
    """
    Calculate estimated time in minutes based on step types and count.

    Args:
        steps: List of transformed steps

    Returns:
        Estimated time in minutes
    """
    if not steps:
        return 0

    # Base time per step type (minutes)
    time_per_type = {
        "investigation": 5,
        "mitigation": 10,
        "resolution": 15,
        "verification": 5,
        "rollback": 10,
    }

    total_time = 0
    for step in steps:
        step_type = step.get("_inferred_step_type", "investigation")
        base_time = time_per_type.get(step_type, 10)
        # Adjust for risk level
        risk_level_raw = step.get("risk_level", "medium")
        risk_level = risk_level_raw.lower() if risk_level_raw else "medium"
        if risk_level == "high":
            base_time = int(base_time * 1.5)
        elif risk_level == "low":
            base_time = int(base_time * 0.8)
        total_time += base_time

    return total_time
