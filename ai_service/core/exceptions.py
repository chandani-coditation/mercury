"""Custom exceptions for NOC Agent AI."""


class NOCAgentError(Exception):
    """Base exception for NOC Agent AI errors."""

    pass


class ValidationError(NOCAgentError):
    """Raised when validation fails (guardrails, schema, etc.)."""

    pass


class TriageValidationError(ValidationError):
    """Raised when triage output validation fails."""

    pass


class ResolutionValidationError(ValidationError):
    """Raised when resolution output validation fails."""

    pass


class IncidentNotFoundError(NOCAgentError):
    """Raised when an incident is not found."""

    pass


class LLMError(NOCAgentError):
    """Raised when LLM API calls fail."""

    pass


class RetrievalError(NOCAgentError):
    """Raised when retrieval/search operations fail."""

    pass


class PolicyError(NOCAgentError):
    """Raised when policy evaluation fails."""

    pass


class DatabaseError(NOCAgentError):
    """Raised when database operations fail."""

    pass


class ConfigurationError(NOCAgentError):
    """Raised when configuration is invalid or missing."""

    pass


class ApprovalRequiredError(NOCAgentError):
    """Raised when user approval is required before proceeding."""

    pass
