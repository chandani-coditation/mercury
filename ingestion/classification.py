"""Rule-based classification for incident signatures.

This module provides deterministic, CSV-driven classification of incidents
into failure types and error classes using explicit rules and controlled vocabularies.
"""

import csv
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

from ai_service.core import get_logger

if TYPE_CHECKING:
    from ingestion.models import IngestIncident

logger = get_logger(__name__)


class PatternType(Enum):
    """Types of pattern matching."""

    KEYWORD = "keyword"
    REGEX = "regex"
    EXACT_MATCH = "exact_match"
    FALLBACK = "fallback"


@dataclass
class ClassificationRule:
    """A single classification rule."""

    rule_id: str
    rule_type: str  # "failure_type" or "error_class"
    priority: int
    pattern_type: PatternType
    pattern: str
    value: str  # The classification value to assign
    context_field: str  # Which fields to search (e.g., "title|description")
    failure_type: Optional[str] = (
        None  # For error_class rules, which failure_type they apply to
    )
    notes: Optional[str] = None


class IncidentClassifier:
    """Rule-based classifier for incidents."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize classifier with rules from CSV files."""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"

        self.config_dir = Path(config_dir)
        self.failure_type_rules: List[ClassificationRule] = []
        self.error_class_rules: List[ClassificationRule] = []
        self.symptom_vocabulary: Dict[str, str] = {}

        self._load_rules()
        self._load_symptom_vocabulary()

    def _load_rules(self):
        """Load classification rules from CSV files."""
        # Load failure type rules
        failure_rules_file = (
            self.config_dir / "incident_classification_rules.csv"
        )
        if failure_rules_file.exists():
            with open(failure_rules_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rule = ClassificationRule(
                        rule_id=row["rule_id"],
                        rule_type=row["rule_type"],
                        priority=int(row["priority"]),
                        pattern_type=PatternType(row["pattern_type"]),
                        pattern=row["pattern"],
                        value=row["value"],
                        context_field=row["context_field"],
                        notes=row.get("notes", ""),
                    )
                    if rule.rule_type == "failure_type":
                        self.failure_type_rules.append(rule)

        # Sort by priority (lower number = higher priority)
        self.failure_type_rules.sort(key=lambda r: r.priority)

        # Load error class rules
        error_rules_file = self.config_dir / "error_classification_rules.csv"
        if error_rules_file.exists():
            with open(error_rules_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rule = ClassificationRule(
                        rule_id=row["rule_id"],
                        rule_type=row["rule_type"],
                        priority=int(row["priority"]),
                        pattern_type=PatternType(row["pattern_type"]),
                        pattern=row["pattern"],
                        value=row["value"],
                        context_field=row["context_field"],
                        failure_type=row.get("failure_type") or None,
                        notes=row.get("notes", ""),
                    )
                    if rule.rule_type == "error_class":
                        self.error_class_rules.append(rule)

        # Sort by priority
        self.error_class_rules.sort(key=lambda r: r.priority)

        logger.info(
            f"Loaded {len(self.failure_type_rules)} failure_type rules and "
            f"{len(self.error_class_rules)} error_class rules"
        )

    def _load_symptom_vocabulary(self):
        """Load symptom normalization vocabulary from CSV."""
        vocab_file = self.config_dir / "symptom_vocabulary.csv"
        if vocab_file.exists():
            with open(vocab_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pattern = row["pattern"]
                    normalized = row["normalized_symptom"]
                    self.symptom_vocabulary[pattern] = normalized

        logger.info(
            f"Loaded {len(self.symptom_vocabulary)} symptom normalization patterns"
        )

    def _extract_text_from_fields(self, incident: "IngestIncident", field_spec: str) -> str:  # type: ignore
        """Extract text from specified fields of an incident."""
        fields = [f.strip() for f in field_spec.split("|")]
        text_parts = []

        for field in fields:
            if field == "title":
                text_parts.append(incident.title or "")
            elif field == "description":
                text_parts.append(incident.description or "")
            elif field == "category":
                text_parts.append(incident.category or "")
            elif field == "root_cause":
                text_parts.append(incident.root_cause or "")

        return " ".join(text_parts)

    def _match_pattern(
        self, text: str, pattern: str, pattern_type: PatternType
    ) -> bool:
        """Match a pattern against text."""
        text_lower = text.lower()

        if pattern_type == PatternType.FALLBACK:
            return True  # Fallback always matches

        if pattern_type == PatternType.KEYWORD:
            # Split pattern by | for OR logic
            keywords = [k.strip() for k in pattern.split("|")]
            return any(keyword.lower() in text_lower for keyword in keywords)

        elif pattern_type == PatternType.REGEX:
            try:
                return bool(re.search(pattern, text, re.IGNORECASE))
            except re.error:
                logger.warning(f"Invalid regex pattern: {pattern}")
                return False

        elif pattern_type == PatternType.EXACT_MATCH:
            return pattern.lower() == text_lower.strip()

        return False

    def classify_failure_type(self, incident: "IngestIncident") -> str:  # type: ignore
        """Classify failure type using rule-based approach."""
        for rule in self.failure_type_rules:
            text = self._extract_text_from_fields(incident, rule.context_field)
            if self._match_pattern(text, rule.pattern, rule.pattern_type):
                logger.debug(
                    f"Matched failure_type rule {rule.rule_id}: {rule.value}"
                )
                return rule.value

        # Should never reach here if fallback rule exists
        return "UNKNOWN_FAILURE"

    def classify_error_class(
        self, incident: "IngestIncident", failure_type: str  # type: ignore
    ) -> str:
        """Classify error class using rule-based approach, considering failure_type."""
        # First, try rules specific to this failure_type
        for rule in self.error_class_rules:
            if rule.failure_type and rule.failure_type != failure_type:
                continue

            text = self._extract_text_from_fields(incident, rule.context_field)
            if self._match_pattern(text, rule.pattern, rule.pattern_type):
                logger.debug(
                    f"Matched error_class rule {rule.rule_id}: {rule.value}"
                )
                return rule.value

        # Should never reach here if fallback rule exists
        return "UNKNOWN_ERROR"

    def normalize_symptoms(self, incident: "IngestIncident") -> List[str]:  # type: ignore
        """Extract and normalize symptoms using controlled vocabulary."""
        text = f"{incident.title or ''} {incident.description or ''}".lower()
        normalized_symptoms = []
        matched_patterns = set()

        # Match patterns in priority order (more specific first)
        for pattern, normalized in sorted(
            self.symptom_vocabulary.items(),
            key=lambda x: len(x[0]),
            reverse=True,  # Longer patterns first (more specific)
        ):
            if pattern in matched_patterns:
                continue

            try:
                if re.search(pattern, text, re.IGNORECASE):
                    normalized_symptoms.append(normalized)
                    matched_patterns.add(pattern)
                    # Limit to prevent too many symptoms
                    if len(normalized_symptoms) >= 5:
                        break
            except re.error:
                logger.warning(
                    f"Invalid regex pattern in symptom vocabulary: {pattern}"
                )

        # If no symptoms found, use a default
        if not normalized_symptoms:
            normalized_symptoms = ["unknown_symptoms"]

        return normalized_symptoms[:5]  # Limit to 5 symptoms

    def generate_signature_id(
        self, incident: "IngestIncident", failure_type: str, error_class: str  # type: ignore
    ) -> str:
        """Generate deterministic hash-based signature ID."""
        # Create a stable hash from key identifying fields
        hash_input = f"{failure_type}:{error_class}:{incident.title or ''}:{incident.incident_id or ''}"
        hash_bytes = hashlib.sha256(hash_input.encode("utf-8")).digest()
        hash_hex = hash_bytes.hex()[
            :12
        ].upper()  # Use first 12 chars for readability

        # Format: SIG-<hash>
        return f"SIG-{hash_hex}"


def get_classifier() -> IncidentClassifier:
    """Get or create the global classifier instance."""
    if not hasattr(get_classifier, "_instance"):
        get_classifier._instance = IncidentClassifier()
    return get_classifier._instance
