"""LLM client for OpenAI with retry logic.

This module provides high-level functions for LLM operations (triage, resolution).
It uses the common LLM handler from ai_service.core.llm_handler which abstracts
away the differences between OpenAI API and Private LLM Gateway.
"""

import json
from ai_service.core import get_llm_config, get_logger, get_llm_handler
from ai_service.prompts import (
    TRIAGE_USER_PROMPT_TEMPLATE,
    TRIAGE_SYSTEM_PROMPT_DEFAULT,
    RESOLUTION_USER_PROMPT_TEMPLATE,
    RESOLUTION_SYSTEM_PROMPT_DEFAULT,
)

logger = get_logger(__name__)


def get_llm_client():
    """
    Get LLM handler instance (for backward compatibility).

    This function is kept for backward compatibility with existing code.
    New code should use get_llm_handler() directly from ai_service.core.

    Returns:
        LLMHandler: The global LLM handler instance
    """
    return get_llm_handler()


def _call_llm_with_retry(handler, request_params, agent_type: str, model: str):
    """
    Call LLM API with retry logic using the common handler.

    Args:
        handler: LLMHandler instance
        request_params: Parameters for the API call
        agent_type: Type of agent (triage or resolution)
        model: Model name for metrics

    Returns:
        API response
    """
    return handler.chat_completions_create(request_params, agent_type=agent_type)


def call_llm_for_triage(alert: dict, triage_evidence: dict, model: str = None) -> dict:
    """
    Call LLM to triage an alert.

    Per architecture: Triage agent receives incident signatures and runbook metadata only.

    Args:
        alert: Alert dictionary
        triage_evidence: Dictionary with 'incident_signatures' and 'runbook_metadata' lists
        model: Optional OpenAI model to use (overrides config if provided)

    Returns:
        Triage output as dictionary matching architecture schema
    """
    handler = get_llm_handler()

    llm_config = get_llm_config()
    triage_config = llm_config.get("triage", {})

    # Use provided model or config, with fallback
    model = model or triage_config.get("model", "gpt-4-turbo-preview")
    temperature = triage_config.get("temperature", 0.3)
    system_prompt = triage_config.get("system_prompt", TRIAGE_SYSTEM_PROMPT_DEFAULT)
    response_format_type = triage_config.get("response_format", "json_object")
    max_tokens = triage_config.get("max_tokens")

    incident_signatures = triage_evidence.get("incident_signatures", [])
    runbook_metadata = triage_evidence.get("runbook_metadata", [])

    context_parts = []

    if incident_signatures:
        context_parts.append("=== INCIDENT SIGNATURES ===")
        for sig in incident_signatures[:5]:  # Top 5 signatures
            metadata = sig.get("metadata", {})
            sig_id = metadata.get("incident_signature_id", "UNKNOWN")
            failure_type = metadata.get("failure_type", "UNKNOWN")
            error_class = metadata.get("error_class", "UNKNOWN")
            symptoms = metadata.get("symptoms", [])
            affected_service = metadata.get("affected_service", "")

            context_parts.append(
                f"Incident Signature ID: {sig_id}\n"
                f"Failure Type: {failure_type}\n"
                f"Error Class: {error_class}\n"
                f"Symptoms: {', '.join(symptoms) if symptoms else 'None'}\n"
                f"Affected Service: {affected_service}\n"
                f"Content: {sig.get('content', '')[:500]}"
            )

    if runbook_metadata:
        context_parts.append("\n=== RUNBOOK METADATA ===")
        for rb in runbook_metadata[:5]:  # Top 5 runbooks
            tags = rb.get("tags", {})
            runbook_id = tags.get("runbook_id", "UNKNOWN")
            failure_types = tags.get("failure_types", [])

            context_parts.append(
                f"Runbook ID: {runbook_id}\n"
                f"Title: {rb.get('title', 'Unknown')}\n"
                f"Service: {rb.get('service', 'Unknown')}\n"
                f"Component: {rb.get('component', 'Unknown')}\n"
                f"Failure Types: {', '.join(failure_types) if failure_types else 'None'}\n"
                f"Last Reviewed: {rb.get('last_reviewed_at', 'Unknown')}"
            )

    context_text = (
        "\n\n---\n\n".join(context_parts) if context_parts else "No matching evidence found."
    )

    prompt = TRIAGE_USER_PROMPT_TEMPLATE.format(
        alert_title=alert["title"],
        alert_description=alert["description"],
        alert_labels=json.dumps(alert.get("labels", {}), indent=2),
        alert_source=alert["source"],
        context_text=context_text,
    )

    request_params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }

    if response_format_type == "json_object":
        request_params["response_format"] = {"type": "json_object"}

    if max_tokens:
        request_params["max_tokens"] = max_tokens

    try:
        response = _call_llm_with_retry(handler, request_params, "triage", model)

        usage = response.usage
        if usage:
            prompt_tokens = usage.prompt_tokens or 0
            completion_tokens = usage.completion_tokens or 0

        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        return result

    except Exception as e:
        logger.error(f"LLM triage failed after retries: {str(e)}", exc_info=True)
        raise


def call_llm_for_resolution(
    alert: dict, triage_output: dict, context_chunks: list, model: str = None
) -> dict:
    """
    Call LLM to generate resolution steps.

    Args:
        alert: Alert dictionary
        triage_output: Previous triage output
        context_chunks: Retrieved context chunks (prefer runbooks)
        model: Optional OpenAI model to use (overrides config if provided)

    Returns:
        Resolution output as dictionary
    """
    handler = get_llm_handler()

    llm_config = get_llm_config()
    resolution_config = llm_config.get("resolution", {})

    model = model or resolution_config.get("model", "gpt-4-turbo-preview")
    temperature = resolution_config.get("temperature", 0.2)
    system_prompt = resolution_config.get("system_prompt", RESOLUTION_SYSTEM_PROMPT_DEFAULT)
    response_format_type = resolution_config.get("response_format", "json_object")
    max_tokens = resolution_config.get("max_tokens")

    context_parts = []
    for chunk in context_chunks[:10]:
        chunk_id = chunk.get("chunk_id", "unknown")
        doc_id = chunk.get("document_id", "unknown")
        doc_title = chunk.get("doc_title", "Unknown")
        context_parts.append(
            f"Document: {doc_title}\n"
            f"Chunk ID: {chunk_id}\n"
            f"Document ID: {doc_id}\n"
            f"Content: {chunk['content']}"
        )
    context_text = "\n\n---\n\n".join(context_parts)

    prompt = RESOLUTION_USER_PROMPT_TEMPLATE.format(
        alert_title=alert["title"],
        alert_description=alert["description"],
        severity=triage_output.get("severity", "unknown"),
        category=triage_output.get("category", "unknown"),
        likely_cause=triage_output.get("likely_cause", "unknown"),
        context_text=context_text,
    )

    request_params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }

    if response_format_type == "json_object":
        request_params["response_format"] = {"type": "json_object"}

    if max_tokens:
        request_params["max_tokens"] = max_tokens

    try:
        response = _call_llm_with_retry(handler, request_params, "resolution", model)

        usage = response.usage
        if usage:
            prompt_tokens = usage.prompt_tokens or 0
            completion_tokens = usage.completion_tokens or 0

        result_text = response.choices[0].message.content
        result = json.loads(result_text)
        return result

    except Exception as e:
        logger.error(f"LLM resolution failed after retries: {str(e)}", exc_info=True)
        raise
