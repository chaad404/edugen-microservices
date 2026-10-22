import pytest

from generator.validation import InvalidOutput, normalized_questions, parse_json_object

QUESTION = {"question": "Which mechanism retransmits a lost segment early?",
            "options": {"A": "Fast retransmit", "B": "Slow start", "C": "Congestion avoidance", "D": "Delayed ACK"},
            "answer": "A"}


def test_the_simulator_is_always_available_real_models_need_a_key(catalog, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert catalog["simulator"].available and not catalog["simulator"].paid
    assert not catalog["gpt-oss"].available
    assert catalog["gpt-oss"].public()["requires"] == "OPENROUTER_API_KEY"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-secret")
    assert catalog["gpt-oss"].available


def test_the_public_view_never_contains_the_key(catalog, monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "very-secret-value")
    assert "very-secret-value" not in str(catalog["cohere"].public())


def test_cost_uses_the_price_per_million_tokens(catalog):
    assert catalog["cohere"].cost(1_000_000, 100_000) == pytest.approx(2.50 + 1.00)
    assert catalog["simulator"].cost(10_000, 10_000) == 0


def test_the_thesis_models_are_pinned_to_one_host(catalog):
    assert catalog["llama33"].routing["order"] == ["coreweave"]
    assert catalog["llama33"].routing["allow_fallbacks"] is False
    assert catalog["mistral-small"].model_id == "mistralai/mistral-small-2603"


@pytest.mark.parametrize("text", [
    '{"questions": []}',
    '```json\n{"questions": []}\n```',
    'Here you go: {"questions": []} Hope it helps!',
])
def test_json_is_parsed_from_common_model_output_shapes(text):
    assert parse_json_object(text) == {"questions": []}


def test_unusable_output_raises_invalid_output():
    with pytest.raises(InvalidOutput):
        parse_json_object("no json here")
    with pytest.raises(InvalidOutput):
        parse_json_object("[1, 2, 3]")


def test_normalized_questions_checks_count_and_shape():
    raw = {"questions": [{**QUESTION, "answer": "a)", "evidence": " quote "}]}
    assert normalized_questions(raw, 1) == [{**QUESTION, "evidence": "quote"}]
    with pytest.raises(InvalidOutput, match="Expected 2 questions"):
        normalized_questions(raw, 2)
    with pytest.raises(InvalidOutput, match="Question 1 invalid"):
        normalized_questions({"questions": [{**QUESTION, "answer": "E"}]}, 1)
