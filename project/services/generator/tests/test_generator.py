import pytest
from fastapi.testclient import TestClient
from project.services.generator.src.main import app
from project.services.generator.src.providers.mock_provider import MockLLMProvider
from project.services.generator.src.schemas import GenerateBatchRequest

client = TestClient(app)

def test_generator_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "edugen-generator"

def test_mock_provider_unit():
    provider = MockLLMProvider()
    req = GenerateBatchRequest(
        topic_id="SYSTEM-2022-1",
        domain="SYSTEM",
        source_text="Control systems and state-space representation.",
        count=3
    )
    questions, tokens, cost = provider.generate(req)
    assert len(questions) == 3
    assert tokens > 0
    assert cost >= 0.0

    for q in questions:
        assert q.question_stem
        assert q.option_a
        assert q.option_b
        assert q.option_c
        assert q.option_d
        assert q.correct_option in ["A", "B", "C", "D"]

def test_generate_batch_endpoint():
    payload = {
        "topic_id": "NETCOMP-2022-3",
        "domain": "NETCOMP",
        "title": "TCP Congestion Control",
        "source_text": "TCP Slow start, congestion avoidance, fast retransmit.",
        "model_name": "mock",
        "strategy": "multi_agent",
        "count": 2
    }
    response = client.post("/generate/batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["topic_id"] == "NETCOMP-2022-3"
    assert len(data["questions"]) == 2
    assert data["tokens_used"] > 0
    assert data["latency_seconds"] >= 0.0
