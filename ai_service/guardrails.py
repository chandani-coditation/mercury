"""Guardrails for AI agent outputs - configuration-driven validation.

Per architecture: This module enforces guardrails to prevent:
1. Hallucination: Agents inventing steps/classifications not from evidence
2. Step Duplication: Same step appearing multiple times
3. Wrong Retrieval: Agents retrieving data outside their boundaries
"""

from typing import Dict, Tuple, List, Optional
import re
from ai_service.core import get_guardrail_config, get_logger

logger = get_logger(__name__)


def validate_triage_output(triage_output: Dict) -> Tuple[bool, List[str]]:
    """
    Validate triage output against architecture schema.

    Per architecture, triage output must have:
    - incident_signature: {failure_type, error_class}
    - matched_evidence: {incident_signatures: [], runbook_refs: []}
    - severity: critical|high|medium|low
    - confidence: 0.0-1.0
    - policy: AUTO|PROPOSE|REVIEW

    Args:
        triage_output: Triage output dictionary from LLM

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    logger.debug("Validating triage output against architecture schema")
    errors = []
    config = get_guardrail_config().get("triage", {})

    # Check required top-level fields (severity, confidence, policy are system-calculated, not from LLM)
    required_fields = ["incident_signature", "matched_evidence"]
    for field in required_fields:
        if field not in triage_output:
            errors.append(f"Missing required field: {field}")
        elif triage_output[field] is None:
            errors.append(f"Required field is None: {field}")

    # Validate incident_signature structure
    incident_sig = triage_output.get("incident_signature")
    if incident_sig:
        if not isinstance(incident_sig, dict):
            errors.append("incident_signature must be a dictionary")
        else:
            if "failure_type" not in incident_sig:
                errors.append("incident_signature.failure_type is required")
            elif not isinstance(incident_sig["failure_type"], str):
                errors.append("incident_signature.failure_type must be a string")

            if "error_class" not in incident_sig:
                errors.append("incident_signature.error_class is required")
            elif not isinstance(incident_sig["error_class"], str):
                errors.append("incident_signature.error_class must be a string")
    else:
        errors.append("incident_signature is required")

    # Validate matched_evidence structure
    matched_evidence = triage_output.get("matched_evidence")
    if matched_evidence:
        if not isinstance(matched_evidence, dict):
            errors.append("matched_evidence must be a dictionary")
        else:
            # Validate incident_signatures array
            incident_sigs = matched_evidence.get("incident_signatures", [])
            if not isinstance(incident_sigs, list):
                errors.append("matched_evidence.incident_signatures must be a list")
            else:
                for i, sig_id in enumerate(incident_sigs):
                    if not isinstance(sig_id, str):
                        errors.append(f"matched_evidence.incident_signatures[{i}] must be a string")

            # Validate runbook_refs array
            runbook_refs = matched_evidence.get("runbook_refs", [])
            if not isinstance(runbook_refs, list):
                errors.append("matched_evidence.runbook_refs must be a list")
            else:
                for i, ref_id in enumerate(runbook_refs):
                    if not isinstance(ref_id, str):
                        errors.append(f"matched_evidence.runbook_refs[{i}] must be a string")
    else:
        errors.append("matched_evidence is required")

    # Note: severity, confidence, and policy are system-calculated (not from LLM)
    # They are validated after post-processing, not from LLM output

    if errors:
        logger.warning(f"Triage validation failed with {len(errors)} errors: {errors}")
    else:
        logger.debug("Triage validation passed")

    return len(errors) == 0, errors


def validate_resolution_output(
    resolution_output: Dict, context_chunks: List[Dict] = None
) -> Tuple[bool, List[str]]:
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
    # Note: risk_level, estimated_time_minutes, and requires_approval are deprecated
    # They are not based on historical data and should not be LLM-generated
    # Allow None values for deprecated fields
    deprecated_fields = {"estimated_time_minutes", "risk_level", "requires_approval"}
    required_fields = config.get("required_fields", [])
    for field in required_fields:
        if field not in resolution_output:
            errors.append(f"Missing required field: {field}")
        elif resolution_output[field] is None and field not in deprecated_fields:
            # Allow None for deprecated fields, but not for other required fields
            errors.append(f"Required field is None: {field}")

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
            total_commands = sum(
                len(cmd_list)
                for cmd_list in commands_by_step.values()
                if isinstance(cmd_list, list)
            )
            if total_commands > max_commands:
                errors.append(
                    f"Too many commands in commands_by_step: {total_commands} (max: {max_commands})"
                )

            # Check for dangerous commands (but allow if from runbooks via provenance)
            dangerous_commands = config.get("dangerous_commands", [])
            provenance = resolution_output.get("provenance", [])
            # Check if any provenance points to runbooks
            has_runbook_provenance = False
            if provenance and runbook_doc_ids:
                for prov in provenance:
                    if (
                        prov.get("doc_id") in runbook_doc_ids
                        or prov.get("chunk_id") in runbook_chunk_ids
                    ):
                        has_runbook_provenance = True
                        break

            for step_idx, cmd_list in commands_by_step.items():
                if not isinstance(cmd_list, list):
                    errors.append(f"commands_by_step['{step_idx}'] must be a list")
                else:
                    for cmd in cmd_list:
                        if not isinstance(cmd, str):
                            errors.append(
                                f"Command in commands_by_step['{step_idx}'] must be a string"
                            )
                        else:
                            cmd_lower = cmd.lower()
                            for dangerous in dangerous_commands:
                                if dangerous.lower() in cmd_lower:
                                    # Allow dangerous commands if they came from runbooks
                                    if has_runbook_provenance:
                                        logger.debug(
                                            f"Allowing dangerous command '{dangerous}' from runbook: '{cmd}'"
                                        )
                                    else:
                                        errors.append(
                                            f"Dangerous command detected: '{dangerous}' in '{cmd}'. Commands must come from runbooks."
                                        )

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
                    if (
                        prov.get("doc_id") in runbook_doc_ids
                        or prov.get("chunk_id") in runbook_chunk_ids
                    ):
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
                                logger.debug(
                                    f"Allowing dangerous command '{dangerous}' from runbook: '{cmd}'"
                                )
                            else:
                                errors.append(
                                    f"Dangerous command detected: '{dangerous}' in '{cmd}'. Commands must come from runbooks."
                                )

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
            errors.append(
                f"reasoning too long: {len(reasoning)} chars (max: {max_reasoning_length})"
            )

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

    # Validate rollback_plan (CRITICAL for production safety)
    rollback_plan = resolution_output.get("rollback_plan")

    # Rollback plan is recommended for all resolutions but not strictly required
    # (risk_level is no longer available to determine requirement)
    if rollback_plan:
        # Validate rollback_plan structure (supports both legacy list and new structured format)
        if isinstance(rollback_plan, list):
            # Legacy format: list of rollback steps
            max_rollback = config.get("max_rollback_steps", 10)
            if len(rollback_plan) > max_rollback:
                errors.append(
                    f"Too many rollback steps: {len(rollback_plan)} (max: {max_rollback})"
                )

            # Recommend using structured format for better safety
            logger.debug("Rollback plan provided in structured format")

        elif isinstance(rollback_plan, dict):
            # New structured format: validate required fields
            rollback_steps = rollback_plan.get("steps")
            if not rollback_steps:
                errors.append("rollback_plan.steps is required in structured format")
            elif not isinstance(rollback_steps, list):
                errors.append("rollback_plan.steps must be a list")
            else:
                max_rollback = config.get("max_rollback_steps", 10)
                if len(rollback_steps) < 1:
                    errors.append("rollback_plan.steps must contain at least 1 step")
                elif len(rollback_steps) > max_rollback:
                    errors.append(
                        f"Too many rollback steps: {len(rollback_steps)} (max: {max_rollback})"
                    )

                # Validate each rollback step is a string
                for i, step in enumerate(rollback_steps):
                    if not isinstance(step, str):
                        errors.append(f"rollback_plan.steps[{i}] must be a string")

            # Validate commands_by_step (optional)
            rollback_commands = rollback_plan.get("commands_by_step")
            if rollback_commands is not None:
                if not isinstance(rollback_commands, dict):
                    errors.append("rollback_plan.commands_by_step must be a dict or null")
                else:
                    for step_idx, cmd_list in rollback_commands.items():
                        if not isinstance(cmd_list, list):
                            errors.append(
                                f"rollback_plan.commands_by_step['{step_idx}'] must be a list"
                            )
                        else:
                            for cmd in cmd_list:
                                if not isinstance(cmd, str):
                                    errors.append(
                                        f"Rollback command in commands_by_step['{step_idx}'] must be a string"
                                    )

            # Validate preconditions (optional but recommended for high risk)
            preconditions = rollback_plan.get("preconditions")
            if preconditions is not None:
                if not isinstance(preconditions, list):
                    errors.append("rollback_plan.preconditions must be a list or null")
                else:
                    for i, precond in enumerate(preconditions):
                        if not isinstance(precond, str):
                            errors.append(f"rollback_plan.preconditions[{i}] must be a string")

            # Strongly recommend preconditions and triggers for all rollback plans
            if not preconditions:
                logger.debug("Rollback plan missing preconditions (recommended for safety)")

            triggers = rollback_plan.get("triggers")
            if not triggers or not isinstance(triggers, list):
                logger.debug("Rollback plan missing triggers (recommended for safety)")

            # Validate triggers (optional)
            triggers = rollback_plan.get("triggers")
            if triggers is not None:
                if not isinstance(triggers, list):
                    errors.append("rollback_plan.triggers must be a list or null")
                else:
                    for i, trigger in enumerate(triggers):
                        if not isinstance(trigger, str):
                            errors.append(f"rollback_plan.triggers[{i}] must be a string")
        else:
            errors.append(
                f"rollback_plan must be a list or dict, got: {type(rollback_plan).__name__}"
            )

    # Even for low-risk, if rollback_plan is provided, validate its structure
    elif rollback_plan is not None:
        if isinstance(rollback_plan, dict):
            # Validate structured format even for low risk
            rollback_steps = rollback_plan.get("steps")
            if rollback_steps and not isinstance(rollback_steps, list):
                errors.append("rollback_plan.steps must be a list")
        elif not isinstance(rollback_plan, list):
            errors.append(
                f"rollback_plan must be a list or dict or null, got: {type(rollback_plan).__name__}"
            )

    if errors:
        logger.warning(
            f"Resolution guardrail validation failed with {len(errors)} errors: {errors}"
        )
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
    destructive_patterns = config.get(
        "destructive_patterns",
        [
            r"\b(drop|delete|truncate|format|rm|remove)\b",
            r"\b(kill|terminate|shutdown)\b",
            r"\b(clear|purge|wipe)\b",
        ],
    )

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


# ============================================================================
# FAILURE MODE GUARDRAILS: Hallucination, Step Duplication, Wrong Retrieval
# ============================================================================


def validate_triage_no_hallucination(
    triage_output: Dict, retrieved_evidence: Optional[Dict] = None
) -> Tuple[bool, List[str]]:
    """
    Validate triage output does NOT contain hallucinated content.

    Per architecture: Triage agent MUST NOT:
    - Generate resolution steps
    - Rank or suggest actions
    - Invent root causes
    - Read runbook steps

    Args:
        triage_output: Triage output dictionary
        retrieved_evidence: Optional evidence dictionary to validate against

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check for forbidden fields that indicate hallucination
    forbidden_fields = [
        "resolution_steps",
        "steps",
        "recommended_actions",
        "actions",
        "fixes",
        "solutions",
        "commands",
        "rollback_plan",
    ]

    for field in forbidden_fields:
        if field in triage_output:
            errors.append(
                f"HALLUCINATION DETECTED: Triage output contains '{field}' field. "
                f"Per architecture, triage agent MUST NOT generate resolution steps."
            )

    # Check incident_signature for invented classifications
    incident_sig = triage_output.get("incident_signature", {})
    if incident_sig:
        failure_type = incident_sig.get("failure_type", "")
        error_class = incident_sig.get("error_class", "")

        # Check if classification matches retrieved evidence
        if retrieved_evidence:
            incident_signatures = retrieved_evidence.get("incident_signatures", [])
            runbook_metadata = retrieved_evidence.get("runbook_metadata", [])

            # If no evidence retrieved, but triage claims high confidence, flag it
            if not incident_signatures and not runbook_metadata:
                confidence = triage_output.get("confidence", 0.0)
                if confidence > 0.5:
                    errors.append(
                        f"HALLUCINATION RISK: High confidence ({confidence}) with no retrieved evidence. "
                        f"Triage agent may be inventing classifications."
                    )

    # Check matched_evidence references exist
    matched_evidence = triage_output.get("matched_evidence", {})
    incident_sig_ids = matched_evidence.get("incident_signatures", [])
    runbook_refs = matched_evidence.get("runbook_refs", [])

    if retrieved_evidence:
        retrieved_sig_ids = set()
        for sig in retrieved_evidence.get("incident_signatures", []):
            # Try multiple ways to get incident_signature_id
            sig_id = None

            # Method 1: Check if it's already at top level (formatted evidence)
            if "incident_signature_id" in sig:
                sig_id = sig.get("incident_signature_id")

            # Method 2: Check in metadata (raw evidence from triage_retrieval)
            if not sig_id:
                metadata = sig.get("metadata", {})
                if isinstance(metadata, dict):
                    sig_id = metadata.get("incident_signature_id")

            # Method 3: Check if metadata is not a dict, try top level
            if not sig_id:
                sig_id = sig.get("incident_signature_id")

            if sig_id:
                retrieved_sig_ids.add(str(sig_id))
        # Extract runbook_ids from multiple possible locations
        retrieved_runbook_ids = set()
        for rb in retrieved_evidence.get("runbook_metadata", []):
            # Try multiple ways to get runbook_id (formatted_evidence has it as direct field)
            rb_id = None
            if "runbook_id" in rb:
                rb_id = rb.get("runbook_id")
            elif "tags" in rb:
                tags = rb.get("tags")
                if isinstance(tags, dict):
                    rb_id = tags.get("runbook_id")
            if rb_id:
                retrieved_runbook_ids.add(str(rb_id))  # Ensure string for comparison

        # Check for references to non-retrieved evidence
        for sig_id in incident_sig_ids:
            if sig_id not in retrieved_sig_ids:
                errors.append(
                    f"WRONG RETRIEVAL: incident_signature_id '{sig_id}' referenced but not retrieved. "
                    f"Triage agent may be hallucinating references."
                )

        for runbook_id in runbook_refs:
            if runbook_id not in retrieved_runbook_ids:
                errors.append(
                    f"WRONG RETRIEVAL: runbook_id '{runbook_id}' referenced but not retrieved. "
                    f"Triage agent may be hallucinating references."
                )

    if errors:
        logger.warning(f"Triage hallucination validation failed: {errors}")
    else:
        logger.debug("Triage hallucination validation passed")

    return len(errors) == 0, errors


def validate_triage_retrieval_boundaries(retrieved_evidence: Dict) -> Tuple[bool, List[str]]:
    """
    Validate triage retrieval respects architecture boundaries.

    Per architecture: Triage agent may ONLY retrieve:
    - Incident signatures (chunks with incident_signature_id)
    - Runbook metadata (documents, NOT runbook steps)

    Args:
        retrieved_evidence: Dictionary with 'incident_signatures' and 'runbook_metadata'

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    incident_signatures = retrieved_evidence.get("incident_signatures", [])
    runbook_metadata = retrieved_evidence.get("runbook_metadata", [])

    # Check incident signatures have incident_signature_id
    for i, sig in enumerate(incident_signatures):
        # Metadata might be a dict or already extracted
        if isinstance(sig.get("metadata"), dict):
            metadata = sig.get("metadata", {})
            sig_id = metadata.get("incident_signature_id")
        else:
            # If metadata is not a dict, check if incident_signature_id is at top level
            sig_id = sig.get("incident_signature_id")

        if not sig_id:
            errors.append(
                f"WRONG RETRIEVAL: Incident signature {i+1} missing 'incident_signature_id' in metadata. "
                f"Triage retrieval should only return chunks with incident_signature_id. "
                f"Available keys: {list(sig.keys())}"
            )

    # Check runbook metadata does NOT contain step chunks
    for i, rb in enumerate(runbook_metadata):
        # Runbook metadata should be document-level, not chunk-level
        if "chunk_id" in rb or "step_id" in rb:
            errors.append(
                f"WRONG RETRIEVAL: Runbook metadata {i+1} contains chunk/step fields. "
                f"Triage agent should only retrieve runbook metadata (documents), NOT runbook steps."
            )

        # Check doc_type is runbook (allow None if not set, as it may be in tags)
        doc_type = rb.get("doc_type")
        if doc_type and doc_type != "runbook":
            errors.append(
                f"WRONG RETRIEVAL: Runbook metadata {i+1} has doc_type '{doc_type}', expected 'runbook'."
            )

    if errors:
        logger.warning(f"Triage retrieval boundary validation failed: {errors}")
    else:
        logger.debug("Triage retrieval boundary validation passed")

    return len(errors) == 0, errors
