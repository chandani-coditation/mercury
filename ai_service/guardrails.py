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
    
    # Validate routing (required field)
    routing = triage_output.get("routing", "")
    if not routing or not routing.strip():
        errors.append("Routing field is required and cannot be empty")
    else:
        max_routing_length = config.get("max_routing_length", 100)
        if len(routing) > max_routing_length:
            errors.append(f"Routing too long: {len(routing)} chars (max: {max_routing_length})")
    
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


def validate_resolution_output(resolution_output: Dict, context_chunks: List[Dict] = None) -> Tuple[bool, List[str]]:
    """
    Validate resolution output against guardrail configuration.
    
    Args:
        resolution_output: Resolution output dictionary from LLM
        context_chunks: Optional list of context chunks used to generate resolution.
                      Used to verify if commands came from runbooks (allowed even if "dangerous")
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    logger.debug("Validating resolution output against guardrails")
    errors = []
    config = get_guardrail_config().get("resolution", {})
    
    # Build a set of runbook document IDs from context chunks for provenance checking
    runbook_doc_ids = set()
    runbook_chunk_ids = set()
    if context_chunks:
        for chunk in context_chunks:
            doc_type = chunk.get("doc_type") or (chunk.get("metadata") or {}).get("doc_type")
            if doc_type == "runbook":
                runbook_doc_ids.add(chunk.get("document_id"))
                runbook_chunk_ids.add(chunk.get("chunk_id"))
    
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
    
    # Validate steps (preferred) or resolution_steps (legacy)
    steps = resolution_output.get("steps", resolution_output.get("resolution_steps", []))
    if not isinstance(steps, list):
        errors.append("steps must be a list")
    else:
        min_steps = config.get("min_resolution_steps", 1)
        max_steps = config.get("max_resolution_steps", 20)
        if len(steps) < min_steps:
            errors.append(f"Too few resolution steps: {len(steps)} (min: {min_steps})")
        elif len(steps) > max_steps:
            errors.append(f"Too many resolution steps: {len(steps)} (max: {max_steps})")
        
        # Validate each step is a string
        for i, step in enumerate(steps):
            if not isinstance(step, str):
                errors.append(f"Resolution step {i+1} must be a string, got: {type(step).__name__}")
    
    # Validate commands_by_step (preferred) or commands (legacy)
    commands_by_step = resolution_output.get("commands_by_step")
    commands = resolution_output.get("commands", [])
    
    if commands_by_step is not None:
        if not isinstance(commands_by_step, dict):
            errors.append("commands_by_step must be a dict or null")
        else:
            max_commands = config.get("max_commands", 10)
            total_commands = sum(len(cmd_list) for cmd_list in commands_by_step.values() if isinstance(cmd_list, list))
            if total_commands > max_commands:
                errors.append(f"Too many commands in commands_by_step: {total_commands} (max: {max_commands})")
            
            # Check for dangerous commands (but allow if from runbooks via provenance)
            dangerous_commands = config.get("dangerous_commands", [])
            provenance = resolution_output.get("provenance", [])
            # Check if any provenance points to runbooks
            has_runbook_provenance = False
            if provenance and runbook_doc_ids:
                for prov in provenance:
                    if prov.get("doc_id") in runbook_doc_ids or prov.get("chunk_id") in runbook_chunk_ids:
                        has_runbook_provenance = True
                        break
            
            for step_idx, cmd_list in commands_by_step.items():
                if not isinstance(cmd_list, list):
                    errors.append(f"commands_by_step['{step_idx}'] must be a list")
                else:
                    for cmd in cmd_list:
                        if not isinstance(cmd, str):
                            errors.append(f"Command in commands_by_step['{step_idx}'] must be a string")
                        else:
                            cmd_lower = cmd.lower()
                            for dangerous in dangerous_commands:
                                if dangerous.lower() in cmd_lower:
                                    # Allow dangerous commands if they came from runbooks
                                    if has_runbook_provenance:
                                        logger.debug(f"Allowing dangerous command '{dangerous}' from runbook: '{cmd}'")
                                    else:
                                        errors.append(f"Dangerous command detected: '{dangerous}' in '{cmd}'. Commands must come from runbooks.")
    
    # Validate legacy commands format (if present and commands_by_step not used)
    if commands is not None and commands_by_step is None:
        if not isinstance(commands, list):
            errors.append("commands must be a list or null")
        else:
            max_commands = config.get("max_commands", 10)
            if len(commands) > max_commands:
                errors.append(f"Too many commands: {len(commands)} (max: {max_commands})")
            
            # Check for dangerous commands (but allow if from runbooks via provenance)
            dangerous_commands = config.get("dangerous_commands", [])
            provenance = resolution_output.get("provenance", [])
            # Check if any provenance points to runbooks
            has_runbook_provenance = False
            if provenance and runbook_doc_ids:
                for prov in provenance:
                    if prov.get("doc_id") in runbook_doc_ids or prov.get("chunk_id") in runbook_chunk_ids:
                        has_runbook_provenance = True
                        break
            
            for cmd in commands:
                if not isinstance(cmd, str):
                    errors.append(f"Command must be a string, got: {type(cmd).__name__}")
                else:
                    cmd_lower = cmd.lower()
                    for dangerous in dangerous_commands:
                        if dangerous.lower() in cmd_lower:
                            # Allow dangerous commands if they came from runbooks
                            if has_runbook_provenance:
                                logger.debug(f"Allowing dangerous command '{dangerous}' from runbook: '{cmd}'")
                            else:
                                errors.append(f"Dangerous command detected: '{dangerous}' in '{cmd}'. Commands must come from runbooks.")
    
    # Validate confidence (optional)
    confidence = resolution_output.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, (int, float)):
            errors.append(f"confidence must be a number, got: {type(confidence).__name__}")
        elif not (0.0 <= confidence <= 1.0):
            errors.append(f"confidence {confidence} out of range [0.0, 1.0]")
    
    # Validate reasoning (optional)
    reasoning = resolution_output.get("reasoning") or resolution_output.get("rationale")
    if reasoning:
        max_reasoning_length = config.get("max_reasoning_length", 1000)
        if len(reasoning) > max_reasoning_length:
            errors.append(f"reasoning too long: {len(reasoning)} chars (max: {max_reasoning_length})")
    
    # Validate provenance (optional)
    provenance = resolution_output.get("provenance")
    if provenance is not None:
        if not isinstance(provenance, list):
            errors.append("provenance must be a list or null")
        else:
            for i, prov in enumerate(provenance):
                if not isinstance(prov, dict):
                    errors.append(f"provenance[{i}] must be a dict")
                else:
                    if "doc_id" not in prov or "chunk_id" not in prov:
                        errors.append(f"provenance[{i}] must contain 'doc_id' and 'chunk_id'")
    
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

