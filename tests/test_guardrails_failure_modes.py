"""Unit tests for guardrails failure mode detection.

Tests cover:
1. Hallucination detection
2. Step duplication detection
3. Wrong retrieval detection
"""

import pytest
from ai_service.guardrails import (
    validate_triage_no_hallucination,
    validate_resolution_no_hallucination,
    validate_no_step_duplication,
    validate_triage_retrieval_boundaries,
    validate_resolution_retrieval_boundaries,
    validate_llm_ranking_no_hallucination,
)


class TestHallucinationDetection:
    """Test hallucination detection in triage and resolution outputs."""

    def test_triage_contains_resolution_steps(self):
        """Test: Triage output should NOT contain resolution steps."""
        triage_output = {
            "incident_signature": {
                "failure_type": "SQL_AGENT_JOB_FAILURE",
                "error_class": "SERVICE_ACCOUNT_DISABLED"
            },
            "matched_evidence": {
                "incident_signatures": ["SIG-DB-001"],
                "runbook_refs": ["RB123"]
            },
            "severity": "medium",
            "confidence": 0.86,
            "policy": "AUTO",
            "steps": ["Step 1: Verify account", "Step 2: Enable account"],  # FORBIDDEN
        }
        
        is_valid, errors = validate_triage_no_hallucination(triage_output)
        
        assert not is_valid
        assert any("resolution_steps" in err or "steps" in err for err in errors)
        assert any("HALLUCINATION" in err for err in errors)

    def test_triage_contains_recommended_actions(self):
        """Test: Triage output should NOT contain recommended_actions."""
        triage_output = {
            "incident_signature": {
                "failure_type": "SQL_AGENT_JOB_FAILURE",
                "error_class": "SERVICE_ACCOUNT_DISABLED"
            },
            "matched_evidence": {
                "incident_signatures": ["SIG-DB-001"],
                "runbook_refs": ["RB123"]
            },
            "severity": "medium",
            "confidence": 0.86,
            "policy": "AUTO",
            "recommended_actions": ["Action 1", "Action 2"],  # FORBIDDEN
        }
        
        is_valid, errors = validate_triage_no_hallucination(triage_output)
        
        assert not is_valid
        assert any("recommended_actions" in err for err in errors)

    def test_triage_high_confidence_with_no_evidence(self):
        """Test: High confidence with no evidence indicates hallucination risk."""
        triage_output = {
            "incident_signature": {
                "failure_type": "SQL_AGENT_JOB_FAILURE",
                "error_class": "SERVICE_ACCOUNT_DISABLED"
            },
            "matched_evidence": {
                "incident_signatures": [],
                "runbook_refs": []
            },
            "severity": "medium",
            "confidence": 0.9,  # High confidence
            "policy": "AUTO",
        }
        
        retrieved_evidence = {
            "incident_signatures": [],
            "runbook_metadata": []
        }
        
        is_valid, errors = validate_triage_no_hallucination(triage_output, retrieved_evidence)
        
        assert not is_valid
        assert any("HALLUCINATION RISK" in err for err in errors)
        assert any("High confidence" in err for err in errors)

    def test_triage_references_non_retrieved_evidence(self):
        """Test: Triage output should NOT reference non-retrieved evidence."""
        triage_output = {
            "incident_signature": {
                "failure_type": "SQL_AGENT_JOB_FAILURE",
                "error_class": "SERVICE_ACCOUNT_DISABLED"
            },
            "matched_evidence": {
                "incident_signatures": ["SIG-DB-001", "SIG-DB-999"],  # SIG-DB-999 not retrieved
                "runbook_refs": ["RB123", "RB999"]  # RB999 not retrieved
            },
            "severity": "medium",
            "confidence": 0.86,
            "policy": "AUTO",
        }
        
        retrieved_evidence = {
            "incident_signatures": [
                {
                    "metadata": {"incident_signature_id": "SIG-DB-001"}
                }
            ],
            "runbook_metadata": [
                {
                    "tags": {"runbook_id": "RB123"}
                }
            ]
        }
        
        is_valid, errors = validate_triage_no_hallucination(triage_output, retrieved_evidence)
        
        assert not is_valid
        assert any("SIG-DB-999" in err for err in errors)
        assert any("RB999" in err for err in errors)
        assert any("WRONG RETRIEVAL" in err for err in errors)

    def test_resolution_invents_new_step_id(self):
        """Test: Resolution should NOT invent new step_ids."""
        resolution_output = {
            "recommendations": [
                {
                    "step_id": "RB123-S3",
                    "action": "Verify service account",
                    "provenance": {
                        "runbook_id": "RB123",
                        "chunk_id": "chunk-123",
                        "step_id": "RB123-S3"
                    }
                },
                {
                    "step_id": "RB999-S1",  # NOT in retrieved steps
                    "action": "Invented step",
                    "provenance": {
                        "runbook_id": "RB999",
                        "chunk_id": "chunk-999",
                        "step_id": "RB999-S1"
                    }
                }
            ]
        }
        
        retrieved_runbook_steps = [
            {
                "step_id": "RB123-S3",
                "chunk_id": "chunk-123",
                "runbook_id": "RB123",
                "action": "Verify service account"
            }
        ]
        
        is_valid, errors = validate_resolution_no_hallucination(
            resolution_output,
            retrieved_runbook_steps,
            []
        )
        
        assert not is_valid
        assert any("RB999-S1" in err for err in errors)
        assert any("HALLUCINATION DETECTED" in err for err in errors)

    def test_resolution_missing_provenance(self):
        """Test: Resolution recommendations must have provenance."""
        resolution_output = {
            "recommendations": [
                {
                    "step_id": "RB123-S3",
                    "action": "Verify service account",
                    # Missing provenance
                }
            ]
        }
        
        retrieved_runbook_steps = [
            {
                "step_id": "RB123-S3",
                "chunk_id": "chunk-123",
                "runbook_id": "RB123"
            }
        ]
        
        is_valid, errors = validate_resolution_no_hallucination(
            resolution_output,
            retrieved_runbook_steps,
            []
        )
        
        assert not is_valid
        assert any("chunk_id" in err for err in errors)
        assert any("INVALID PROVENANCE" in err for err in errors)

    def test_llm_adds_new_step(self):
        """Test: LLM ranking should NOT add new steps."""
        algorithmic_recommendations = [
            {
                "step_id": "RB123-S3",
                "action": "Verify service account",
                "confidence": 0.9
            },
            {
                "step_id": "RB123-S4",
                "action": "Enable account",
                "confidence": 0.85
            }
        ]
        
        llm_recommendations = [
            {
                "step_id": "RB123-S3",
                "action": "Verify service account",
                "confidence": 0.95
            },
            {
                "step_id": "RB999-S1",  # NOT in algorithmic recommendations
                "action": "Invented step",
                "confidence": 0.8
            }
        ]
        
        is_valid, errors = validate_llm_ranking_no_hallucination(
            llm_recommendations,
            algorithmic_recommendations
        )
        
        assert not is_valid
        assert any("RB999-S1" in err for err in errors)
        assert any("LLM HALLUCINATION" in err for err in errors)


class TestStepDuplicationDetection:
    """Test step duplication detection."""

    def test_duplicate_step_ids(self):
        """Test: Recommendations should NOT have duplicate step_ids."""
        recommendations = [
            {
                "step_id": "RB123-S3",
                "action": "Verify service account",
                "confidence": 0.9
            },
            {
                "step_id": "RB123-S4",
                "action": "Enable account",
                "confidence": 0.85
            },
            {
                "step_id": "RB123-S3",  # DUPLICATE
                "action": "Verify service account",
                "confidence": 0.9
            }
        ]
        
        is_valid, errors = validate_no_step_duplication(recommendations)
        
        assert not is_valid
        assert any("RB123-S3" in err for err in errors)
        assert any("STEP DUPLICATION" in err for err in errors)

    def test_duplicate_actions(self):
        """Test: Recommendations with duplicate actions should warn."""
        recommendations = [
            {
                "step_id": "RB123-S3",
                "action": "Verify service account is enabled",
                "confidence": 0.9
            },
            {
                "step_id": "RB123-S4",
                "action": "Verify service account is enabled",  # Duplicate action
                "confidence": 0.85
            }
        ]
        
        is_valid, errors = validate_no_step_duplication(recommendations)
        
        # Duplicate actions are warnings, not errors
        assert is_valid  # No errors (duplicate step_ids)
        assert any("duplicate action" in err.lower() for err in errors)  # But has warnings

    def test_no_duplication_valid(self):
        """Test: Valid recommendations with no duplicates."""
        recommendations = [
            {
                "step_id": "RB123-S3",
                "action": "Verify service account",
                "confidence": 0.9
            },
            {
                "step_id": "RB123-S4",
                "action": "Enable account",
                "confidence": 0.85
            }
        ]
        
        is_valid, errors = validate_no_step_duplication(recommendations)
        
        assert is_valid
        assert len(errors) == 0


class TestWrongRetrievalDetection:
    """Test wrong retrieval detection."""

    def test_triage_retrieves_runbook_steps(self):
        """Test: Triage should NOT retrieve runbook steps."""
        retrieved_evidence = {
            "incident_signatures": [
                {
                    "metadata": {"incident_signature_id": "SIG-DB-001"}
                }
            ],
            "runbook_metadata": [
                {
                    "document_id": "doc-123",
                    "doc_type": "runbook",
                    "chunk_id": "chunk-123",  # FORBIDDEN: chunks should not be in metadata
                    "step_id": "RB123-S3"  # FORBIDDEN: steps should not be in metadata
                }
            ]
        }
        
        is_valid, errors = validate_triage_retrieval_boundaries(retrieved_evidence)
        
        assert not is_valid
        assert any("chunk_id" in err or "step_id" in err for err in errors)
        assert any("WRONG RETRIEVAL" in err for err in errors)

    def test_triage_incident_signature_missing_id(self):
        """Test: Incident signatures must have incident_signature_id."""
        retrieved_evidence = {
            "incident_signatures": [
                {
                    "metadata": {}  # Missing incident_signature_id
                }
            ],
            "runbook_metadata": []
        }
        
        is_valid, errors = validate_triage_retrieval_boundaries(retrieved_evidence)
        
        assert not is_valid
        assert any("incident_signature_id" in err for err in errors)

    def test_triage_runbook_metadata_wrong_doc_type(self):
        """Test: Runbook metadata must have doc_type='runbook'."""
        retrieved_evidence = {
            "incident_signatures": [],
            "runbook_metadata": [
                {
                    "document_id": "doc-123",
                    "doc_type": "incident_signature",  # WRONG
                }
            ]
        }
        
        is_valid, errors = validate_triage_retrieval_boundaries(retrieved_evidence)
        
        assert not is_valid
        assert any("doc_type" in err for err in errors)

    def test_resolution_retrieves_wrong_runbook_id(self):
        """Test: Resolution should only retrieve runbook steps for expected runbook_ids."""
        retrieved_runbook_steps = [
            {
                "step_id": "RB123-S3",
                "runbook_id": "RB123",
                "chunk_id": "chunk-123"
            },
            {
                "step_id": "RB999-S1",  # RB999 not in expected list
                "runbook_id": "RB999",
                "chunk_id": "chunk-999"
            }
        ]
        
        expected_runbook_ids = ["RB123"]
        expected_incident_signature_ids = ["SIG-DB-001"]
        
        is_valid, errors = validate_resolution_retrieval_boundaries(
            retrieved_runbook_steps,
            [],
            expected_runbook_ids,
            expected_incident_signature_ids
        )
        
        assert not is_valid
        assert any("RB999" in err for err in errors)
        assert any("WRONG RETRIEVAL" in err for err in errors)

    def test_resolution_runbook_step_missing_step_id(self):
        """Test: Resolution runbook steps must have step_id."""
        retrieved_runbook_steps = [
            {
                # Missing step_id
                "runbook_id": "RB123",
                "chunk_id": "chunk-123",
                "action": "Verify account"
            }
        ]
        
        expected_runbook_ids = ["RB123"]
        expected_incident_signature_ids = []
        
        is_valid, errors = validate_resolution_retrieval_boundaries(
            retrieved_runbook_steps,
            [],
            expected_runbook_ids,
            expected_incident_signature_ids
        )
        
        assert not is_valid
        assert any("step_id" in err for err in errors)

    def test_triage_retrieval_valid(self):
        """Test: Valid triage retrieval."""
        retrieved_evidence = {
            "incident_signatures": [
                {
                    "metadata": {"incident_signature_id": "SIG-DB-001"}
                }
            ],
            "runbook_metadata": [
                {
                    "document_id": "doc-123",
                    "doc_type": "runbook",
                    "title": "Database Runbook",
                    "tags": {"runbook_id": "RB123"}
                }
            ]
        }
        
        is_valid, errors = validate_triage_retrieval_boundaries(retrieved_evidence)
        
        assert is_valid
        assert len(errors) == 0

    def test_resolution_retrieval_valid(self):
        """Test: Valid resolution retrieval."""
        retrieved_runbook_steps = [
            {
                "step_id": "RB123-S3",
                "runbook_id": "RB123",
                "chunk_id": "chunk-123",
                "action": "Verify account"
            }
        ]
        
        expected_runbook_ids = ["RB123"]
        expected_incident_signature_ids = ["SIG-DB-001"]
        
        is_valid, errors = validate_resolution_retrieval_boundaries(
            retrieved_runbook_steps,
            [],
            expected_runbook_ids,
            expected_incident_signature_ids
        )
        
        assert is_valid
        assert len(errors) == 0


class TestIntegrationScenarios:
    """Integration tests for real-world failure scenarios."""

    def test_triage_hallucinates_resolution_steps(self):
        """Integration: Triage agent hallucinates resolution steps."""
        triage_output = {
            "incident_signature": {
                "failure_type": "SQL_AGENT_JOB_FAILURE",
                "error_class": "SERVICE_ACCOUNT_DISABLED"
            },
            "matched_evidence": {
                "incident_signatures": ["SIG-DB-001"],
                "runbook_refs": ["RB123"]
            },
            "severity": "medium",
            "confidence": 0.86,
            "policy": "AUTO",
            "steps": ["Step 1", "Step 2"],  # FORBIDDEN
            "commands": ["command1", "command2"]  # FORBIDDEN
        }
        
        is_valid, errors = validate_triage_no_hallucination(triage_output)
        
        assert not is_valid
        assert len(errors) >= 2  # At least 2 errors (steps and commands)

    def test_resolution_duplicates_and_hallucinates(self):
        """Integration: Resolution agent duplicates steps and invents new ones."""
        resolution_output = {
            "recommendations": [
                {
                    "step_id": "RB123-S3",
                    "action": "Verify account",
                    "provenance": {"chunk_id": "chunk-123", "runbook_id": "RB123"}
                },
                {
                    "step_id": "RB123-S3",  # DUPLICATE
                    "action": "Verify account",
                    "provenance": {"chunk_id": "chunk-123", "runbook_id": "RB123"}
                },
                {
                    "step_id": "RB999-S1",  # HALLUCINATED
                    "action": "Invented step",
                    "provenance": {"chunk_id": "chunk-999", "runbook_id": "RB999"}
                }
            ]
        }
        
        retrieved_runbook_steps = [
            {
                "step_id": "RB123-S3",
                "chunk_id": "chunk-123",
                "runbook_id": "RB123"
            }
        ]
        
        # Test duplication
        is_valid_dup, dup_errors = validate_no_step_duplication(
            resolution_output["recommendations"]
        )
        assert not is_valid_dup
        
        # Test hallucination
        is_valid_hall, hall_errors = validate_resolution_no_hallucination(
            resolution_output,
            retrieved_runbook_steps,
            []
        )
        assert not is_valid_hall

    def test_wrong_retrieval_chain(self):
        """Integration: Wrong retrieval in triage leads to wrong resolution."""
        # Triage retrieves runbook steps (should only get metadata)
        triage_evidence = {
            "incident_signatures": [],
            "runbook_metadata": [
                {
                    "document_id": "doc-123",
                    "doc_type": "runbook",
                    "chunk_id": "chunk-123",  # FORBIDDEN
                    "step_id": "RB123-S3"  # FORBIDDEN
                }
            ]
        }
        
        is_valid, errors = validate_triage_retrieval_boundaries(triage_evidence)
        assert not is_valid

