from __future__ import annotations

from agents import graph as graph_module
from agents.state import create_initial_state


def test_graph_routes_unrelated_query_directly_to_reporter(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        graph_module,
        "intent_analyzer_node",
        lambda _state: {
            "intent": "unrelated",
            "should_retrieve": False,
            "should_perceive": False,
        },
    )
    monkeypatch.setattr(
        graph_module,
        "retrieve_node",
        lambda _state: calls.append("retriever") or {},
    )
    monkeypatch.setattr(
        graph_module,
        "perception_node",
        lambda _state: calls.append("perceptor") or {},
    )
    monkeypatch.setattr(
        graph_module,
        "generate_report_node",
        lambda _state: calls.append("reporter") or {"report": "ok", "trace": []},
    )
    monkeypatch.setattr(
        graph_module,
        "medical_review_node",
        lambda _state: calls.append("reviewer") or {"review_status": "skipped"},
    )

    graph = graph_module.create_medical_graph()
    graph.invoke(create_initial_state(query="帮我写一首歌"))

    assert calls == ["reporter"]


def test_graph_routes_to_retriever_only(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        graph_module,
        "intent_analyzer_node",
        lambda _state: {
            "intent": "clinical",
            "should_retrieve": True,
            "should_perceive": False,
        },
    )
    monkeypatch.setattr(
        graph_module,
        "retrieve_node",
        lambda _state: calls.append("retriever") or {"trace": []},
    )
    monkeypatch.setattr(
        graph_module,
        "perception_node",
        lambda _state: calls.append("perceptor") or {"trace": []},
    )
    monkeypatch.setattr(
        graph_module,
        "generate_report_node",
        lambda _state: calls.append("reporter") or {"report": "ok", "trace": []},
    )
    monkeypatch.setattr(
        graph_module,
        "medical_review_node",
        lambda _state: calls.append("reviewer") or {"review_status": "skipped"},
    )

    graph = graph_module.create_medical_graph()
    graph.invoke(create_initial_state(query="治疗建议", reviewer_enabled=False))

    assert calls == ["retriever", "reporter"]


def test_graph_routes_to_perceptor_only(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        graph_module,
        "intent_analyzer_node",
        lambda _state: {
            "intent": "clinical",
            "should_retrieve": False,
            "should_perceive": True,
        },
    )
    monkeypatch.setattr(
        graph_module,
        "retrieve_node",
        lambda _state: calls.append("retriever") or {"trace": []},
    )
    monkeypatch.setattr(
        graph_module,
        "perception_node",
        lambda _state: calls.append("perceptor") or {"trace": []},
    )
    monkeypatch.setattr(
        graph_module,
        "generate_report_node",
        lambda _state: calls.append("reporter") or {"report": "ok", "trace": []},
    )
    monkeypatch.setattr(
        graph_module,
        "medical_review_node",
        lambda _state: calls.append("reviewer") or {"review_status": "skipped"},
    )

    graph = graph_module.create_medical_graph()
    graph.invoke(create_initial_state(query="请结合影像", image_path="scan.nii.gz", reviewer_enabled=False))

    assert calls == ["perceptor", "reporter"]
