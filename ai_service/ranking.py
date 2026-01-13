"""Ranking logic for Resolution Agent.

Per architecture: Steps are ranked by:
- Historical success
- Risk level
- Relevance to incident signature
"""

from typing import List, Dict
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
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config" / "step_classification.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    _STEP_CLASSIFICATION_CONFIG = json.load(f)
            else:
                _STEP_CLASSIFICATION_CONFIG = {}
                logger.warning("step_classification.json not found, using defaults")
        except Exception as e:
            logger.warning(f"Failed to load step_classification.json: {e}")
            _STEP_CLASSIFICATION_CONFIG = {}
    return _STEP_CLASSIFICATION_CONFIG


def _get_risk_level_keywords():
    """Get risk level keywords from config."""
    config = _load_step_classification_config()
    risk_levels = config.get("risk_levels", {})
    return {
        "high_risk": risk_levels.get("high_risk_keywords", {}).get(
            "keywords", ["kill", "delete", "drop", "remove", "stop", "restart"]
        ),
        "medium_risk": risk_levels.get("medium_risk_keywords", {}).get(
            "keywords", ["update", "modify", "change", "alter"]
        ),
    }


def _get_condition_text_exclusions():
    """Get condition text exclusions from config."""
    config = _load_step_classification_config()
    return config.get("condition_text_exclusions", {}).get(
        "exclusions", ["step applies", "n/a", ""]
    )


def _clean_action_for_plain_english(action: str) -> str:
    """
    Clean action text to remove SQL queries, commands, and technical code.
    Convert to plain English instructions.

    Args:
        action: Raw action text that may contain SQL, commands, or technical details

    Returns:
        Cleaned plain English action description
    """
    if not action:
        return action

    # Remove SQL queries (lines starting with SELECT, INSERT, UPDATE, DELETE, etc.)
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
        # Skip command-line commands (lines starting with $, #, or common command patterns)
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
    cleaned = re.sub(r"\$[^\s]+", "", cleaned)  # Remove command-line patterns like $command

    return cleaned.strip()


def rank_steps(
    steps: List[Dict],
    incident_signature: Dict,
    historical_resolutions: List[Dict],
    step_success_stats: Dict[str, Dict],
) -> List[Dict]:
    """
    Rank runbook steps by relevance, historical success, and risk.

    Per architecture: Steps are ranked, not invented.

    Args:
        steps: List of runbook step chunks
        incident_signature: Incident signature from triage output
        historical_resolutions: Historical resolution records
        step_success_stats: Success statistics per step_id

    Returns:
        List of ranked steps with scores and provenance
    """
    if not steps:
        return []

    failure_type = incident_signature.get("failure_type", "").lower()
    error_class = incident_signature.get("error_class", "").lower()

    # Score each step
    scored_steps = []

    # Keywords that indicate high relevance for disk/IO/SQL Agent issues
    high_relevance_keywords = [
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
        "transaction",
        "growth",
        "clean",
        "free",
        "remove",
        "sql agent",
        "agent job",
        "job failure",
        "connection",
        "wait",
    ]

    for step in steps:
        step_id = step.get("step_id", "")
        action = (step.get("action") or "").lower() if step.get("action") else ""
        condition = (step.get("condition") or "").lower() if step.get("condition") else ""
        risk_level = (
            (step.get("risk_level") or "medium").lower() if step.get("risk_level") else "medium"
        )
        content = (step.get("content") or "").lower() if step.get("content") else ""

        # Boost relevance if step mentions high-relevance keywords
        step_text = f"{action} {condition} {content}".lower()
        keyword_boost = 0.0
        for keyword in high_relevance_keywords:
            if keyword in step_text:
                keyword_boost += 0.1  # Boost for each matching keyword
                break  # Only count once per step

        # Initialize scores
        relevance_score = 0.0
        success_score = 0.0
        risk_score = 0.0

        # 1. Relevance score (0.0 - 1.0)
        # Check if step condition/action matches failure_type or error_class
        if failure_type and failure_type in condition:
            relevance_score += 0.4
        if failure_type and failure_type in action:
            relevance_score += 0.3
        if error_class and error_class in condition:
            relevance_score += 0.2
        if error_class and error_class in action:
            relevance_score += 0.1

        # Check content relevance
        if failure_type and failure_type in content:
            relevance_score += 0.2
        if error_class and error_class in content:
            relevance_score += 0.1

        # Apply keyword boost for disk/IO/log/tempdb related issues
        relevance_score = min(1.0, relevance_score + keyword_boost)

        # Cap relevance at 1.0
        relevance_score = min(relevance_score, 1.0)

        # If no explicit match, give base relevance based on runbook match
        if relevance_score == 0.0:
            relevance_score = (
                0.5  # Base relevance if step is from matched runbook (increased from 0.3)
            )

        # 2. Historical success score (0.0 - 1.0)
        if step_id in step_success_stats:
            stats = step_success_stats[step_id]
            success_score = stats.get("success_rate", 0.5)

            # Boost for frequently used steps (more data = more reliable)
            if stats.get("total_uses", 0) > 3:
                success_score = min(success_score * 1.1, 1.0)
        else:
            # No history = slightly positive score (steps from runbooks are generally reliable)
            success_score = 0.6  # Increased from 0.5 to reflect runbook reliability

        # Check historical resolutions for step usage patterns
        step_mentioned_count = 0
        step_successful_count = 0

        for hist_res in historical_resolutions:
            resolution_output = hist_res.get("resolution_output", {})
            steps_list = resolution_output.get("steps", [])

            # Check if this step is mentioned in historical resolution
            step_found = any(
                step_id in str(step_text)
                or action in str(step_text).lower()
                or step.get("chunk_id") in str(resolution_output.get("provenance", []))
                for step_text in steps_list
            )

            if step_found:
                step_mentioned_count += 1
                if hist_res.get("is_successful", False):
                    step_successful_count += 1

        # Update success score based on historical resolutions
        if step_mentioned_count > 0:
            hist_success_rate = step_successful_count / step_mentioned_count
            # Blend with existing success score
            success_score = (success_score * 0.6) + (hist_success_rate * 0.4)

        # 3. Risk score (inverted: lower risk = higher score)
        risk_map = {"low": 1.0, "medium": 0.7, "high": 0.4}
        risk_score = risk_map.get(risk_level, 0.7)

        # Combined score (weighted)
        # Relevance: 40%, Success: 40%, Risk: 20%
        combined_score = relevance_score * 0.4 + success_score * 0.4 + risk_score * 0.2

        scored_steps.append(
            {
                **step,
                "relevance_score": relevance_score,
                "success_score": success_score,
                "risk_score": risk_score,
                "combined_score": combined_score,
            }
        )

    # Sort by combined score (descending)
    ranked_steps = sorted(scored_steps, key=lambda x: x["combined_score"], reverse=True)

    return ranked_steps


def assemble_recommendations(
    ranked_steps: List[Dict], min_confidence: float = 0.6, max_steps: int = 10
) -> List[Dict]:
    """
    Assemble ordered recommendations from ranked steps.

    Per architecture: Recommendations must have provenance.

    Args:
        ranked_steps: List of ranked steps with scores
        min_confidence: Minimum confidence threshold
        max_steps: Maximum number of steps to include

    Returns:
        List of recommendation objects with provenance
    """
    recommendations = []

    for step in ranked_steps[:max_steps]:
        # Only include steps above confidence threshold
        if step["combined_score"] < min_confidence:
            continue

        # Build a more descriptive action from condition and action
        action_text = step.get("action", "")
        condition_text = step.get("condition", "")

        # Create a natural language action description
        if action_text and condition_text:
            # Combine condition and action into a more descriptive step
            if condition_text.lower() not in ["step applies", "n/a", ""]:
                enhanced_action = f"{condition_text}. {action_text}"
            else:
                enhanced_action = action_text
        elif action_text:
            enhanced_action = action_text
        elif condition_text:
            enhanced_action = condition_text
        else:
            enhanced_action = f"Execute step {step.get('step_id', 'unknown')}"

        # Ensure we have expected_outcome and risk_level (no rollback needed)
        expected_outcome = step.get("expected_outcome")
        if not expected_outcome and action_text:
            # Generate a reasonable expected outcome from the action
            expected_outcome = f"The issue is resolved and {action_text.lower()}"

        # Remove any SQL queries or technical commands from action
        # Clean up action to be plain English only
        enhanced_action = _clean_action_for_plain_english(enhanced_action)

        risk_level = step.get("risk_level")
        if not risk_level:
            # Infer risk level from action content
            action_lower = enhanced_action.lower()
            risk_keywords = _get_risk_level_keywords()
            if any(word in action_lower for word in risk_keywords["high_risk"]):
                risk_level = "high"
            elif any(word in action_lower for word in risk_keywords["medium_risk"]):
                risk_level = "medium"
            else:
                risk_level = "low"

        condition_exclusions = _get_condition_text_exclusions()
        recommendation = {
            "step_id": step.get("step_id"),
            "action": enhanced_action,
            "condition": (
                condition_text
                if condition_text
                and condition_text.lower() not in [excl.lower() for excl in condition_exclusions]
                else None
            ),
            "expected_outcome": expected_outcome,
            "risk_level": risk_level,
            "confidence": step["combined_score"],
            "provenance": {
                "runbook_id": step.get("runbook_id"),
                "chunk_id": step.get("chunk_id"),
                "document_id": step.get("document_id"),
                "step_id": step.get("step_id"),
            },
            "scores": {
                "relevance": step["relevance_score"],
                "success": step["success_score"],
                "risk": step["risk_score"],
            },
        }

        recommendations.append(recommendation)

    return recommendations
