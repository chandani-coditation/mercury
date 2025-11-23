"""Guardrails for AI agent outputs - configuration-driven validation."""
from typing import Dict, Tuple, List
import re
from ai_service.core import get_guardrail_config, get_logger

logger = get_logger(__name__)


def validate_triage_output(triage_output: Dict) -> Tuple[bool, List[str]]:
    """
    Validate triage output against guardrail configuration.
    
    Args:
        triage_output: Triage output dictionary from LLM
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    logger.debug("Validating triage output against guardrails")
    errors = []
    config = get_guardrail_config().get("triage", {})
    
    # Check required fields
    required_fields = config.get("required_fields", [])
    for field in required_fields:
        if field not in triage_output:
            errors.append(f"Missing required field: {field}")
        elif triage_output[field] is None:
            errors.append(f"Required field is None: {field}")
    
    # Validate severity
    severity = triage_output.get("severity", "").lower()
    allowed_severities = [s.lower() for s in config.get("severity_values", [])]
    if severity not in allowed_severities:
        errors.append(f"Invalid severity '{severity}'. Must be one of: {allowed_severities}")
    
    # Validate category
    category = triage_output.get("category", "").lower()
    allowed_categories = [c.lower() for c in config.get("category_values", [])]
    if category not in allowed_categories:
        errors.append(f"Invalid category '{category}'. Must be one of: {allowed_categories}")
    
    # Validate confidence range
    confidence = triage_output.get("confidence")
    if confidence is not None:
        confidence_range = config.get("confidence_range", [0.0, 1.0])
        if not isinstance(confidence, (int, float)):
            errors.append(f"Confidence must be a number, got: {type(confidence).__name__}")
        elif not (confidence_range[0] <= confidence <= confidence_range[1]):
            errors.append(f"Confidence {confidence} out of range [{confidence_range[0]}, {confidence_range[1]}]")
    
    # Validate string lengths
    summary = triage_output.get("summary", "")
    if summary:
        max_summary_length = config.get("max_summary_length", 500)
        if len(summary) > max_summary_length:
            errors.append(f"Summary too long: {len(summary)} chars (max: {max_summary_length})")
    
    likely_cause = triage_output.get("likely_cause", "")
    if likely_cause:
        max_cause_length = config.get("max_likely_cause_length", 300)
        if len(likely_cause) > max_cause_length:
            errors.append(f"Likely cause too long: {len(likely_cause)} chars (max: {max_cause_length})")
    
    # Validate array lengths
    affected_services = triage_output.get("affected_services", [])
    if not isinstance(affected_services, list):
        errors.append("affected_services must be a list")
    else:
        max_services = config.get("max_affected_services", 10)
        if len(affected_services) > max_services:
            errors.append(f"Too many affected services: {len(affected_services)} (max: {max_services})")
    
    recommended_actions = triage_output.get("recommended_actions", [])
    if not isinstance(recommended_actions, list):
        errors.append("recommended_actions must be a list")
    else:
        max_actions = config.get("max_recommended_actions", 10)
        if len(recommended_actions) > max_actions:
            errors.append(f"Too many recommended actions: {len(recommended_actions)} (max: {max_actions})")
    
    return len(errors) == 0, errors


def validate_resolution_output(resolution_output: Dict) -> Tuple[bool, List[str]]:
    """
    Validate resolution output against guardrail configuration.
    
    Args:
        resolution_output: Resolution output dictionary from LLM
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    logger.debug("Validating resolution output against guardrails")
    errors = []
    config = get_guardrail_config().get("resolution", {})
    
    # Check required fields
    required_fields = config.get("required_fields", [])
    for field in required_fields:
        if field not in resolution_output:
            errors.append(f"Missing required field: {field}")
        elif resolution_output[field] is None:
            errors.append(f"Required field is None: {field}")
    
    # Validate risk_level
    risk_level = resolution_output.get("risk_level", "").lower()
    allowed_risk_levels = [r.lower() for r in config.get("risk_level_values", [])]
    if risk_level not in allowed_risk_levels:
        errors.append(f"Invalid risk_level '{risk_level}'. Must be one of: {allowed_risk_levels}")
    
    # Validate estimated_time_minutes
    estimated_time = resolution_output.get("estimated_time_minutes")
    if estimated_time is not None:
        min_time = config.get("min_estimated_time_minutes", 1)
        max_time = config.get("max_estimated_time_minutes", 1440)
        if not isinstance(estimated_time, int):
            errors.append(f"estimated_time_minutes must be an integer, got: {type(estimated_time).__name__}")
        elif not (min_time <= estimated_time <= max_time):
            errors.append(f"estimated_time_minutes {estimated_time} out of range [{min_time}, {max_time}]")
    
    # Validate resolution_steps
    resolution_steps = resolution_output.get("resolution_steps", [])
    if not isinstance(resolution_steps, list):
        errors.append("resolution_steps must be a list")
    else:
        min_steps = config.get("min_resolution_steps", 1)
        max_steps = config.get("max_resolution_steps", 20)
        if len(resolution_steps) < min_steps:
            errors.append(f"Too few resolution steps: {len(resolution_steps)} (min: {min_steps})")
        elif len(resolution_steps) > max_steps:
            errors.append(f"Too many resolution steps: {len(resolution_steps)} (max: {max_steps})")
        
        # Validate each step is a string
        for i, step in enumerate(resolution_steps):
            if not isinstance(step, str):
                errors.append(f"Resolution step {i+1} must be a string, got: {type(step).__name__}")
    
    # Validate commands (if present)
    commands = resolution_output.get("commands", [])
    if commands is not None:
        if not isinstance(commands, list):
            errors.append("commands must be a list or null")
        else:
            max_commands = config.get("max_commands", 10)
            if len(commands) > max_commands:
                errors.append(f"Too many commands: {len(commands)} (max: {max_commands})")
            
            # Check for dangerous commands
            dangerous_commands = config.get("dangerous_commands", [])
            for cmd in commands:
                if not isinstance(cmd, str):
                    errors.append(f"Command must be a string, got: {type(cmd).__name__}")
                else:
                    cmd_lower = cmd.lower()
                    for dangerous in dangerous_commands:
                        if dangerous.lower() in cmd_lower:
                            errors.append(f"Dangerous command detected: '{dangerous}' in '{cmd}'")
    
    # Validate rollback_plan (if high risk)
    risk_level_upper = resolution_output.get("risk_level", "").lower()
    require_rollback_for = [r.lower() for r in config.get("require_rollback_for_risk_levels", [])]
    if risk_level_upper in require_rollback_for:
        rollback_plan = resolution_output.get("rollback_plan")
        if not rollback_plan:
            errors.append(f"rollback_plan required for risk_level '{risk_level_upper}'")
        elif isinstance(rollback_plan, list):
            max_rollback = config.get("max_rollback_steps", 10)
            if len(rollback_plan) > max_rollback:
                errors.append(f"Too many rollback steps: {len(rollback_plan)} (max: {max_rollback})")
    
    if errors:
        logger.warning(f"Resolution guardrail validation failed with {len(errors)} errors: {errors}")
    else:
        logger.debug("Resolution guardrail validation passed")
    return len(errors) == 0, errors


def validate_command(command: str) -> bool:
    """
    Validate a single command against dangerous command patterns.
    
    Args:
        command: Command string to validate
    
    Returns:
        True if safe, False if dangerous
    """
    config = get_guardrail_config().get("resolution", {})
    dangerous_commands = config.get("dangerous_commands", [])
    
    cmd_lower = command.lower()
    for dangerous in dangerous_commands:
        if dangerous.lower() in cmd_lower:
            return False
    
    return True


def check_destructive_operations(steps: List[str]) -> List[str]:
    """
    Check resolution steps for destructive operations.
    
    Uses configurable destructive patterns from config/guardrails.json.
    
    Args:
        steps: List of resolution step strings
    
    Returns:
        List of warnings for potentially destructive operations
    """
    warnings = []
    config = get_guardrail_config().get("resolution", {})
    
    # Get destructive patterns from config (with defaults)
    destructive_patterns = config.get("destructive_patterns", [
        r"\b(drop|delete|truncate|format|rm|remove)\b",
        r"\b(kill|terminate|shutdown)\b",
        r"\b(clear|purge|wipe)\b"
    ])
    
    for i, step in enumerate(steps):
        step_lower = step.lower()
        for pattern in destructive_patterns:
            # Compile pattern if it's a string (regex)
            try:
                if isinstance(pattern, str):
                    compiled_pattern = re.compile(pattern, re.IGNORECASE)
                else:
                    compiled_pattern = pattern
                
                if compiled_pattern.search(step_lower):
                    warnings.append(f"Step {i+1} may be destructive: '{step[:50]}...'")
                    break
            except re.error:
                # If pattern is invalid, skip it
                continue
    
    return warnings

