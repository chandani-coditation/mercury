"""Query text enhancement utilities for better retrieval."""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# Load technical terms config
_technical_terms_config = None
_extraction_patterns_config = None
_ingestion_config = None


def _load_technical_terms_config():
    """Load technical terms configuration from config file."""
    global _technical_terms_config
    if _technical_terms_config is None:
        try:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "technical_terms.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    _technical_terms_config = json.load(f)
            else:
                _technical_terms_config = {"abbreviations": {}, "synonyms": {}}
        except Exception:
            _technical_terms_config = {"abbreviations": {}, "synonyms": {}}
    return _technical_terms_config


def _load_extraction_patterns_config():
    """Load extraction patterns configuration from config file."""
    global _extraction_patterns_config
    if _extraction_patterns_config is None:
        try:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "extraction_patterns.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    _extraction_patterns_config = json.load(f)
            else:
                _extraction_patterns_config = {
                    "error_code_patterns": [],
                    "job_patterns": [],
                    "id_patterns": [],
                    "service_patterns": [],
                }
        except Exception:
            _extraction_patterns_config = {
                "error_code_patterns": [],
                "job_patterns": [],
                "id_patterns": [],
                "service_patterns": [],
            }
    return _extraction_patterns_config


def _load_ingestion_config():
    """Load ingestion configuration from config file."""
    global _ingestion_config
    if _ingestion_config is None:
        try:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "ingestion.json"
            if config_path.exists():
                with open(config_path, "r") as f:
                    _ingestion_config = json.load(f)
            else:
                _ingestion_config = {"formatting": {}}
        except Exception:
            _ingestion_config = {"formatting": {}}
    return _ingestion_config


def extract_technical_terms(text: str) -> List[str]:
    """
    Extract technical terms from text (error codes, job names, service names, etc.).

    Args:
        text: Input text to extract terms from

    Returns:
        List of extracted technical terms
    """
    terms = []

    # Load patterns from config (centralized)
    patterns_config = _load_extraction_patterns_config()
    ingestion_config = _load_ingestion_config()

    error_code_patterns = patterns_config.get("error_code_patterns", [])
    job_patterns = patterns_config.get("job_patterns", [])
    service_patterns = patterns_config.get("service_patterns", [])
    error_code_prefix = ingestion_config.get("formatting", {}).get("error_code_prefix", "error")

    # Extract error codes (e.g., "Error 500", "SQLSTATE 23505", "HTTP 404")
    for pattern_str in error_code_patterns:
        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            matches = pattern.findall(text)
            terms.extend([f"{error_code_prefix} {m}" for m in matches])
        except Exception:
            # Skip invalid pattern (graceful degradation)
            continue

    # Extract job/process names (quoted strings, capitalized words after "job", "process", "task")
    for pattern_str in job_patterns:
        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            matches = pattern.findall(text)
            terms.extend(matches)
        except Exception:
            # Skip invalid pattern (graceful degradation)
            continue

    # Extract service/component names (capitalized words, hyphenated)
    for pattern_str in service_patterns:
        try:
            pattern = re.compile(pattern_str)
            matches = pattern.findall(text)
            terms.extend(matches)
        except Exception:
            # Skip invalid pattern (graceful degradation)
            continue

    return list(set(terms))  # Remove duplicates


def expand_abbreviations(text: str) -> str:
    """
    Expand common abbreviations in text using config file.

    **Soft Rule**: This is an enhancement that gracefully degrades if config is missing
    or expansion fails. If expansion fails, returns original text unchanged.

    Args:
        text: Input text with potential abbreviations

    Returns:
        Text with abbreviations expanded (or original text if expansion fails)
    """
    if not text:
        return text

    try:
        config = _load_technical_terms_config()
        abbreviations = config.get("abbreviations", {})

        if not abbreviations:
            # No config available - return original text (graceful degradation)
            return text

        expanded_text = text
        for abbrev, expansion in abbreviations.items():
            try:
                # Create regex pattern for word boundary
                pattern = r"\b" + re.escape(abbrev) + r"\b"
                expanded_text = re.sub(pattern, expansion, expanded_text, flags=re.IGNORECASE)
            except Exception:
                # Skip this abbreviation if regex fails (graceful degradation)
                continue

        return expanded_text
    except Exception:
        # If any error occurs, return original text (graceful degradation)
        return text


def add_synonyms(text: str) -> str:
    """
    Add synonyms for common terms to improve recall using config file.

    **Soft Rule**: This is an enhancement that gracefully degrades if config is missing
    or synonym expansion fails. If expansion fails, returns original text unchanged.

    Args:
        text: Input text

    Returns:
        Text with synonyms added (or original text if expansion fails)
    """
    if not text:
        return text

    try:
        config = _load_technical_terms_config()
        synonyms_map = config.get("synonyms", {})

        if not synonyms_map:
            # No config available - return original text (graceful degradation)
            return text

        enhanced_text = text
        for term, synonyms in synonyms_map.items():
            try:
                # Create regex pattern for word boundary
                pattern = r"\b" + re.escape(term) + r"\b"
                if re.search(pattern, text, re.IGNORECASE):
                    # Add synonyms after the original term
                    enhanced_text = re.sub(
                        pattern,
                        lambda m: f"{m.group(0)} {' '.join(synonyms)}",
                        enhanced_text,
                        flags=re.IGNORECASE,
                    )
            except Exception:
                # Skip this synonym if regex fails (graceful degradation)
                continue

        return enhanced_text
    except Exception:
        # If any error occurs, return original text (graceful degradation)
        return text


def normalize_query_text(text: str) -> str:
    """
    Normalize query text by cleaning whitespace and punctuation.

    Args:
        text: Input query text

    Returns:
        Normalized query text
    """
    if not text:
        return ""

    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove multiple periods
    text = re.sub(r"\.\s*\.+", ".", text)
    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def enhance_query(alert: Dict[str, Any]) -> str:
    """
    Enhance query text from alert for better retrieval.

    Combines title, description, and extracted technical terms.
    Applies abbreviation expansion and synonym addition.

    Args:
        alert: Alert dictionary with title, description, labels, etc.

    Returns:
        Enhanced query text
    """
    title = alert.get("title", "") or ""
    description = alert.get("description", "") or ""

    # Extract technical terms
    technical_terms = []
    if description:
        technical_terms.extend(extract_technical_terms(description))
    if title:
        technical_terms.extend(extract_technical_terms(title))

    # Combine title and description
    query_parts = []
    if title:
        query_parts.append(title)
    if description:
        query_parts.append(description)

    # Add technical terms
    if technical_terms:
        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term in technical_terms:
            term_lower = term.lower().strip()
            if term_lower and term_lower not in seen:
                seen.add(term_lower)
                unique_terms.append(term.strip())
        query_parts.extend(unique_terms)

    # Join parts
    query_text = " ".join(query_parts)

    # Expand abbreviations
    query_text = expand_abbreviations(query_text)

    # Add synonyms (for better recall)
    query_text = add_synonyms(query_text)

    # Normalize
    query_text = normalize_query_text(query_text)

    return query_text
