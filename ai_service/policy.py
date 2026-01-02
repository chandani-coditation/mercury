"""Policy gates for resolution actions - configuration-driven."""

from typing import Dict, Optional
from ai_service.core import get_policy_config, get_logger

logger = get_logger(__name__)


def evaluate_condition(condition: Dict, triage_output: Dict) -> bool:
    """
    Evaluate a single policy condition.

    Args:
        condition: Condition dict like {"severity": ["low"]} or {"confidence": "> 0.9"}
        triage_output: Triage output dictionary

    Returns:
        True if condition matches, False otherwise
    """
    for key, value in condition.items():
        if key == "severity":
            # Check if severity is in allowed list
            severity = triage_output.get("severity", "").lower()
            allowed = [v.lower() for v in value] if isinstance(value, list) else [value.lower()]
            if severity not in allowed:
                return False

        elif key == "confidence":
            # Evaluate confidence comparison (e.g., "> 0.9", ">= 0.7")
            confidence = triage_output.get("confidence", 0.0)
            if not isinstance(confidence, (int, float)):
                return False

            # Parse comparison operator
            if isinstance(value, str):
                if value.startswith(">="):
                    threshold = float(value[2:].strip())
                    if confidence < threshold:
                        return False
                elif value.startswith("<="):
                    threshold = float(value[2:].strip())
                    if confidence > threshold:
                        return False
                elif value.startswith(">"):
                    threshold = float(value[1:].strip())
                    if confidence <= threshold:
                        return False
                elif value.startswith("<"):
                    threshold = float(value[1:].strip())
                    if confidence >= threshold:
                        return False
                elif value.startswith("=="):
                    threshold = float(value[2:].strip())
                    if confidence != threshold:
                        return False
                else:
                    # Try direct comparison
                    threshold = float(value)
                    if confidence != threshold:
                        return False

        elif key == "risk_level":
            # For policy gate after triage, we don't have risk_level yet
            # This will be checked after resolution is generated
            # For now, we'll skip this condition in triage-based policy
            pass

    return True


def get_policy_from_config(triage_output: Dict) -> Dict:
    """
    Get policy decision from configuration based on triage output.

    This runs AFTER triage to determine policy_band.
    Policy bands are evaluated in order: AUTO, PROPOSE, REVIEW

    Args:
        triage_output: Triage output dictionary

    Returns:
        Policy dictionary with policy_band and policy_decision
    """
    severity = triage_output.get("severity", "unknown")
    confidence = triage_output.get("confidence", 0.0)
    logger.debug(f"Evaluating policy for triage: severity={severity}, confidence={confidence}")

    config = get_policy_config()
    bands = config.get("bands", {})
    evaluation_order = config.get("evaluation_order", ["AUTO", "PROPOSE", "REVIEW"])
    logger.debug(
        f"Policy config loaded: {len(bands)} bands available, evaluation_order={evaluation_order}"
    )

    # Try each band in order until we find a match
    for band_name in evaluation_order:
        band_config = bands.get(band_name, {})
        conditions = band_config.get("conditions", [])

        # Check if all conditions match
        all_conditions_match = True
        for condition in conditions:
            if not evaluate_condition(condition, triage_output):
                all_conditions_match = False
                break

        if all_conditions_match:
            # Found matching band
            actions = band_config.get("actions", {})
            # Create a more descriptive policy reason
            severity_display = severity.capitalize() if severity else "Unknown"
            confidence_display = f"{confidence:.1%}" if isinstance(confidence, (int, float)) else str(confidence)
            policy_reason = f"Matched {band_name} band based on severity={severity_display} and confidence={confidence_display}"
            
            policy_decision = {
                "policy_band": band_name,
                "original_policy_band": band_name,  # Track original system-determined policy band
                "can_auto_apply": actions.get("can_auto_apply", False),
                "requires_approval": actions.get("requires_approval", True),
                "notification_required": actions.get("notification_required", False),
                "rollback_required": actions.get("rollback_required", False),
                "policy_reason": policy_reason,
            }
            logger.info(
                f"Policy band matched: {band_name} for severity={severity}, confidence={confidence}"
            )
            return policy_decision

    # Default to REVIEW if no band matches (expected for zero-evidence alerts with confidence=0.0)
    default_band = bands.get("REVIEW", {}).get("actions", {})
    logger.debug(
        f"No policy band matched for severity={severity}, confidence={confidence}, defaulting to REVIEW (expected for zero-evidence alerts)"
    )
    return {
        "policy_band": "REVIEW",
        "original_policy_band": "REVIEW",  # Track original system-determined policy band
        "can_auto_apply": default_band.get("can_auto_apply", False),
        "requires_approval": default_band.get("requires_approval", True),
        "notification_required": default_band.get("notification_required", True),
        "rollback_required": default_band.get("rollback_required", True),
        "policy_reason": "No policy band matched, defaulting to REVIEW",
    }


def get_resolution_policy(severity: str, risk_level: str) -> Dict:
    """
    Get policy for resolution based on severity and risk level.

    This is a fallback function when policy decision is not available from triage.
    The preferred method is to use get_policy_from_config() after triage.

    Args:
        severity: Alert severity (from triage)
        risk_level: Resolution risk level (from resolution output)

    Returns:
        Policy dictionary with rules
    """
    # Create a mock triage output for evaluation
    triage_output = {
        "severity": severity,
        "confidence": 0.8,  # Default confidence
        "risk_level": risk_level,  # Note: risk_level comes from resolution, not triage
    }

    # Use config-driven policy
    policy = get_policy_from_config(triage_output)

    # Override rollback_required based on risk_level
    if risk_level in ["high", "critical"]:
        policy["rollback_required"] = True

    return policy


def should_auto_apply_resolution(resolution_output: Dict) -> bool:
    """
    Determine if resolution can be auto-applied based on policy.

    This is a fallback function. Policy decisions should come from
    get_policy_from_config() which runs after triage.

    Args:
        resolution_output: Resolution output dictionary

    Returns:
        True if can auto-apply, False if needs approval
    """
    risk_level = resolution_output.get("risk_level", "high").lower()
    requires_approval = resolution_output.get("requires_approval", True)

    # If explicitly requires approval, don't auto-apply
    if requires_approval:
        return False

    # High risk always requires approval
    if risk_level == "high":
        return False

    # Low and medium risk can auto-apply
    return True
