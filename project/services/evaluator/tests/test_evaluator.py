import pytest
from fastapi.testclient import TestClient
from project.services.evaluator.src.main import app
from project.services.evaluator.src.metrics import (
    calculate_semantic_alignment,
    calculate_linguistic_complexity,
    calculate_distractor_plausibility,
    calculate_distractor_diversity
)
from project.services.evaluator.src.schemas import MCQItem
from project.services.evaluator.src.quality_gate import audit_quality_gate

client = TestClient(app)

SAMPLE_SYLLABUS = """
In the Transmission Control Protocol (TCP), congestion control is implemented using four core algorithms:
Slow Start, Congestion Avoidance, Fast Retransmit, and Fast Recovery. The slow start threshold (ssthresh)
determines whether the sender operates in exponential growth or linear congestion avoidance mode.
"""

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "edugen-evaluator"

def test_pillar1_semantic_alignment():
    relevant_stem = "How does TCP slow start threshold (ssthresh) affect congestion control mode transitions?"
    irrelevant_stem = "What is the capital city of France during the Renaissance era?"

    score_rel = calculate_semantic_alignment(SAMPLE_SYLLABUS, relevant_stem)
    score_irrel = calculate_semantic_alignment(SAMPLE_SYLLABUS, irrelevant_stem)

    assert score_rel > 0.40, f"Expected high alignment for relevant stem, got {score_rel}"
    assert score_irrel == 0.0, f"Expected 0.0 alignment for completely irrelevant stem, got {score_irrel}"

def test_pillar2_linguistic_complexity():
    stem = "The Transmission Control Protocol ensures reliable in-order byte stream delivery across unreliable networks."
    grade, ease = calculate_linguistic_complexity(stem)
    assert grade > 8.0
    assert isinstance(ease, float)

def test_pillar3_distractor_plausibility():
    key = "Congestion Avoidance algorithm"
    plausible_foils = [
        "Slow Start algorithm",
        "Fast Recovery algorithm",
        "Fast Retransmit algorithm"
    ]
    trivial_foils = [
        "Photosynthesis",
        "Internal combustion engine",
        "Quantum superposition"
    ]

    score_plausible = calculate_distractor_plausibility(key, plausible_foils)
    score_trivial = calculate_distractor_plausibility(key, trivial_foils)

    assert score_plausible > score_trivial
    assert score_trivial == 0.0

def test_quality_gate_duplicate_detection():
    defective_item = MCQItem(
        question_stem="What protocol operates at the transport layer?",
        option_a="TCP",
        option_b="UDP",
        option_c="TCP",  # Duplicate!
        option_d="ICMP",
        correct_option="A"
    )
    passed, flags = audit_quality_gate(defective_item, semantic_alignment=0.5)
    assert not passed
    assert any("DUPLICATE_OPTIONS" in f for f in flags)

def test_evaluate_item_api():
    payload = {
        "source_text": SAMPLE_SYLLABUS,
        "question": {
            "question_stem": "Which TCP congestion control algorithm switches to linear growth upon reaching ssthresh?",
            "option_a": "Congestion Avoidance",
            "option_b": "Slow Start",
            "option_c": "Fast Retransmit",
            "option_d": "Three-way handshake",
            "correct_option": "A",
            "explanation": "Once Congestion Window reaches ssthresh, TCP switches from Slow Start to Congestion Avoidance."
        }
    }
    response = client.post("/evaluate/item", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["semantic_alignment"] > 0.3
    assert data["linguistic_complexity"] > 0
    assert data["quality_gate_passed"] is True
    assert len(data["flags"]) == 0

def test_evaluate_batch_api():
    payload = {
        "source_text": SAMPLE_SYLLABUS,
        "questions": [
            {
                "question_stem": "What threshold governs TCP transition from exponential growth to linear growth?",
                "option_a": "ssthresh",
                "option_b": "max_window",
                "option_c": "rtt_min",
                "option_d": "mtu_limit",
                "correct_option": "A"
            },
            {
                "question_stem": "Which mechanism enables fast retransmission in TCP without waiting for a retransmission timeout?",
                "option_a": "Triple duplicate ACKs",
                "option_b": "SYN cookies",
                "option_c": "Nagle algorithm",
                "option_d": "Delayed ACKs",
                "correct_option": "A"
            }
        ]
    }
    response = client.post("/evaluate/batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_questions"] == 2
    assert data["mean_semantic_alignment"] > 0.1
    assert len(data["results"]) == 2
