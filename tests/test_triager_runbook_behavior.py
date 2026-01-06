import sys
import os
from typing import List, Dict, Any

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_service.agents.triager import _triage_agent_internal  # noqa: E402


class DummyRepo:
    """Simple in-memory IncidentRepository replacement for unit tests."""

    def __init__(self):
        self.created = []

    def create(self, alert: Dict[str, Any], triage_output: Dict[str, Any], triage_evidence: Dict[str, Any],
               policy_band: str, policy_decision: Dict[str, Any]) -> str:
        incident_id = f"test-{len(self.created) + 1}"
        self.created.append(
            {
                "incident_id": incident_id,
                "alert": alert,
                "triage_output": triage_output,
                "triage_evidence": triage_evidence,
                "policy_band": policy_band,
                "policy_decision": policy_decision,
            }
        )
        return incident_id


def _make_alert(title: str, description: str, service: str = None, component: str = None) -> Dict[str, Any]:
    labels = {}
    if service:
        labels["service"] = service
    if component:
        labels["component"] = component
    return {
        "alert_id": "test-alert-1",
        "source": "prometheus",
        "title": title,
        "description": description,
        "labels": labels,
    }


@pytest.fixture
def patch_repo(monkeypatch):
    repo = DummyRepo()
    monkeypatch.setattr("ai_service.agents.triager.IncidentRepository", lambda: repo)
    return repo


def _patch_db_count(monkeypatch, count: int):
    class DummyCursor:
        def execute(self, *args, **kwargs):
            pass

        def fetchone(self):
            return {"count": count}

        def close(self):
            pass

    class DummyConn:
        def cursor(self):
            return DummyCursor()

        def close(self):
            pass

    monkeypatch.setattr(
        "ai_service.agents.triager.get_db_connection",
        lambda: DummyConn(),
    )


def test_triager_prefers_runbooks_when_available(monkeypatch, patch_repo):
    """When both incident and runbook chunks are available, runbooks should be present and preferred in context."""

    def fake_hybrid_search(query_text: str, service=None, component=None, limit: int = 5,
                           vector_weight: float = 0.7, fulltext_weight: float = 0.3) -> List[Dict[str, Any]]:
        return [
            {
                "chunk_id": "rb-1",
                "document_id": "doc-runbook-1",
                "chunk_index": 0,
                "content": "Runbook: Steps to resolve high CPU on database.",
                "metadata": {"doc_type": "runbook", "service": "database", "component": "cpu"},
                "doc_title": "Runbook - Database High CPU",
                "doc_type": "runbook",
                "vector_score": 0.9,
                "fulltext_score": 0.5,
                "rrf_score": 0.9,
            },
            {
                "chunk_id": "inc-1",
                "document_id": "doc-incident-1",
                "chunk_index": 0,
                "content": "Incident ticket without clear resolution steps.",
                "metadata": {"doc_type": "incident", "service": "database", "component": "cpu"},
                "doc_title": "Incident - Historical CPU ticket",
                "doc_type": "incident",
                "vector_score": 0.7,
                "fulltext_score": 0.4,
                "rrf_score": 0.8,
            },
        ]

    monkeypatch.setattr("ai_service.agents.triager.hybrid_search", fake_hybrid_search)

    def fake_call_llm(alert: Dict[str, Any], chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Assert that at least one runbook chunk is present in the context
        doc_types = {ch.get("doc_type") for ch in chunks}
        assert "runbook" in doc_types
        # Minimal valid triage response
        return {
            "severity": "high",
            "category": "database",
            "summary": "Test triage summary",
            "likely_cause": "Test cause",
            "routing": "SE DBA SQL",
            "affected_services": ["database"],
            "recommended_actions": ["Follow steps from runbook."],
            "confidence": 0.9,
        }

    monkeypatch.setattr("ai_service.agents.triager.call_llm_for_triage", fake_call_llm)

    alert = _make_alert(
        title="High CPU on database",
        description="CPU usage above 90% for 15 minutes.",
        service="database",
        component="cpu",
    )

    result = _triage_agent_internal(alert)

    assert result["context_chunks_used"] == 2
    assert result["triage"]["confidence"] == 0.9
    # Policy band still comes from config/policy.json in this path, so we just assert it's present
    assert result["policy_band"] in {"AUTO", "PROPOSE", "REVIEW"}


def test_triager_runbook_fallback_used_when_primary_search_empty(monkeypatch, patch_repo):
    """When primary search returns no chunks but fallback finds runbooks, triager should use them under REVIEW."""

    calls = {"primary": 0, "fallback": 0}

    def fake_hybrid_search(query_text: str, service=None, component=None, limit: int = 5,
                           vector_weight: float = 0.7, fulltext_weight: float = 0.3) -> List[Dict[str, Any]]:
        # Primary call: with service/component filters → no results
        if service is not None or component is not None:
            calls["primary"] += 1
            return []
        # Fallback call: relaxed filters → runbook-only result
        calls["fallback"] += 1
        return [
            {
                "chunk_id": "rb-fallback-1",
                "document_id": "doc-runbook-fallback-1",
                "chunk_index": 0,
                "content": "Runbook: Generic steps for database CPU issues.",
                "metadata": {"doc_type": "runbook"},
                "doc_title": "Runbook - Generic Database CPU",
                "doc_type": "runbook",
                "vector_score": 0.8,
                "fulltext_score": 0.5,
                "rrf_score": 0.8,
            }
        ]

    monkeypatch.setattr("ai_service.agents.triager.hybrid_search", fake_hybrid_search)

    def fake_call_llm(alert: Dict[str, Any], chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        # In fallback path, only runbook chunks should be present
        assert len(chunks) == 1
        assert chunks[0].get("doc_type") == "runbook"
        return {
            "severity": "medium",
            "category": "database",
            "summary": "Fallback triage with runbook context",
            "likely_cause": "Database CPU saturation",
            "routing": "SE DBA SQL",
            "affected_services": ["database"],
            "recommended_actions": ["Follow generic database CPU runbook."],
            "confidence": 0.7,
        }

    monkeypatch.setattr("ai_service.agents.triager.call_llm_for_triage", fake_call_llm)

    alert = _make_alert(
        title="Database CPU alert",
        description="CPU usage on database node is high.",
        service="db-service",
        component="db-node",
    )

    result = _triage_agent_internal(alert)

    assert calls["primary"] == 1
    assert calls["fallback"] == 1
    assert result["context_chunks_used"] == 1
    assert result["triage"]["confidence"] == 0.7
    # Fallback path should force REVIEW band and require approval
    assert result["policy_band"] == "REVIEW"
    assert result["policy_decision"]["requires_approval"] is True


def test_triager_generic_review_when_no_evidence_anywhere(monkeypatch, patch_repo):
    """When neither primary nor fallback search returns chunks, triager should return generic REVIEW with confidence 0.0."""

    def fake_hybrid_search(query_text: str, service=None, component=None, limit: int = 5,
                           vector_weight: float = 0.7, fulltext_weight: float = 0.3) -> List[Dict[str, Any]]:
        return []

    monkeypatch.setattr("ai_service.agents.triager.hybrid_search", fake_hybrid_search)

    # Ensure documents table appears non-empty so we hit the "no matching evidence" message
    _patch_db_count(monkeypatch, count=10)

    alert = _make_alert(
        title="Unknown alert",
        description="Totally novel alert with no matching KB.",
        service="mystery-service",
        component="mystery-component",
    )

    result = _triage_agent_internal(alert)

    triage = result["triage"]
    assert triage["confidence"] == 0.0
    assert result["policy_band"] == "REVIEW"
    # Evidence should be empty in this case
    assert result["context_chunks_used"] == 0
    assert result["evidence_chunks"]["chunks_used"] == 0





