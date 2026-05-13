from __future__ import annotations

from agents import nodes


def test_intent_analyzer_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(nodes.config, "LLM_API_KEY", "")

    result = nodes.intent_analyzer_node(
        {
            "query": "肝癌下一步怎么处理？",
            "image_path": "/tmp/example.nii.gz",
            "job_id": "",
        }
    )

    assert result["intent"] == "clinical"
    assert result["should_retrieve"] is True
    assert result["should_perceive"] is True
    assert result["workflow_status"] == "running"
    assert result["trace"][0]["node"] == "analyzer"
    assert result["trace"][0]["status"] == "completed"
    assert result["warnings"]


def test_retrieve_node_skips_when_disabled():
    result = nodes.retrieve_node(
        {
            "query": "test",
            "should_retrieve": False,
            "job_id": "",
        }
    )

    assert result["retrieved_docs"] == []
    assert result["evidence"] == []
    assert result["trace"][0]["status"] == "skipped"


def test_perception_node_uses_placeholder_when_model_missing(monkeypatch, tmp_path):
    image_file = tmp_path / "scan.nii.gz"
    image_file.write_bytes(b"fake")

    monkeypatch.setattr(nodes.config, "PERCEPTION_MODEL_PATH", str(tmp_path / "missing-model.pt"))

    result = nodes.perception_node(
        {
            "query": "test",
            "job_id": "",
            "image_path": str(image_file),
            "should_perceive": True,
        }
    )

    assert result["perception_status"] == "placeholder"
    assert "unavailable" in result["perception_data"].lower()
    assert result["preview_image"] is None
    assert result["warnings"]


def test_generate_report_returns_guardrail_for_unrelated_query():
    result = nodes.generate_report_node(
        {
            "query": "帮我写一首歌",
            "intent": "unrelated",
            "warnings": [],
            "errors": [],
            "evidence": [],
            "job_id": "",
        }
    )

    assert "medical" in result["report"].lower()
    assert result["workflow_status"] == "completed"
    assert result["review_status"] == "skipped"


def test_medical_review_skips_when_disabled():
    result = nodes.medical_review_node(
        {
            "query": "test",
            "report": "report",
            "reviewer_enabled": False,
            "job_id": "",
        }
    )

    assert result["review_status"] == "skipped"
    assert result["is_medical_valid"] is True
    assert result["workflow_status"] == "completed"
