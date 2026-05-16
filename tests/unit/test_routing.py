from __future__ import annotations

from agents import routing


def test_analyze_intent_routing_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(routing.config, "LLM_API_KEY", "")

    result = routing.analyze_intent_routing(
        "please review this case",
        "/tmp/example.nii.gz",
    )

    assert result["intent"] == "clinical"
    assert result["should_retrieve"] is True
    assert result["should_perceive"] is True
    assert result["routing_mode"] == "fallback"
    assert result["warnings"]
    assert result["errors"] == []


def test_analyze_intent_routing_parses_llm_response(monkeypatch):
    monkeypatch.setattr(routing.config, "LLM_API_KEY", "test-key")

    class DummyResponse:
        content = "intent=education;retrieve=yes;perceive=no"

    class DummyLLM:
        def invoke(self, prompt):
            return DummyResponse()

    monkeypatch.setattr(routing, "_logic_llm", DummyLLM())

    result = routing.analyze_intent_routing(
        "summarize guideline updates",
        "/tmp/example.nii.gz",
    )

    assert result["intent"] == "education"
    assert result["should_retrieve"] is True
    assert result["should_perceive"] is False
    assert result["routing_mode"] == "llm"
    assert result["warnings"] == []
    assert result["errors"] == []
