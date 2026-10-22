import json
import random
from collections import Counter

import pytest

from conftest import TOPIC_TEXT, FakeEvaluator, ScriptedProvider, client_for, make_job, provider_error
from generator import prompts
from generator.evaluator_client import Verdict
from generator.llm import GenerationFailed
from generator.providers.simulator import SimulatorProvider
from generator.strategies import balanced_positions, baseline, prompt_v2, select, shuffle_batch, verify_repair
from generator.validation import normalized_questions


def simulator_client(catalog, max_attempts=3):
    return client_for(catalog["simulator"], SimulatorProvider(catalog["simulator"]), max_attempts)


def _q(stem, answer="A"):
    return {"question": stem, "options": {"A": "alpha one", "B": "beta two", "C": "gamma three", "D": "delta four"},
            "answer": answer}


def test_balanced_positions_use_every_letter_equally():
    assert Counter(balanced_positions(8, random.Random(3))) == {"A": 2, "B": 2, "C": 2, "D": 2}


def test_shuffle_batch_balances_keys_keeps_key_text_and_is_deterministic():
    questions = [_q(f"Question number {i} about slow start?") for i in range(8)]
    first = shuffle_batch(questions, "T1", "llama33", "prompt_v2")
    assert Counter(q["answer"] for q in first) == {"A": 2, "B": 2, "C": 2, "D": 2}
    assert all(q["options"][q["answer"]] == "alpha one" for q in first)
    assert first == shuffle_batch(questions, "T1", "llama33", "prompt_v2")


def test_the_simulator_answers_prompts_like_a_model(catalog):
    sim = SimulatorProvider(catalog["simulator"])
    for messages in (prompts.v1_messages(TOPIC_TEXT, 4), prompts.v2_messages(TOPIC_TEXT, 4)):
        result = sim.chat(messages, json_mode=True)
        items = normalized_questions(json.loads(result.text), 4)
        assert all(item["evidence"] in " ".join(TOPIC_TEXT.split()) for item in items)
        assert sim.chat(messages, json_mode=True).text == result.text  # deterministic


def test_the_simulator_rewrites_the_options_named_in_a_repair(catalog):
    sim = SimulatorProvider(catalog["simulator"])
    item = normalized_questions(json.loads(sim.chat(prompts.v2_messages(TOPIC_TEXT, 1), True).text), 1)[0]
    target = next(label for label in "ABCD" if label != item["answer"])
    repaired = json.loads(sim.chat(prompts.repair_messages(TOPIC_TEXT, [item], [[f"weak:{target}"]]), True).text)
    new = repaired["questions"][0]
    assert new["options"][target] != item["options"][target]
    assert new["answer"] == item["answer"] and new["options"][item["answer"]] == item["options"][item["answer"]]


def test_baseline_uses_the_v1_prompt_and_keeps_the_model_order(catalog):
    outcome = baseline(make_job(), simulator_client(catalog))
    assert len(outcome.items) == 3 and outcome.status == "valid" and outcome.usage.calls == 1


def test_prompt_v2_balances_the_keys(catalog):
    outcome = prompt_v2(make_job(num_questions=8, strategy="prompt_v2"), simulator_client(catalog))
    assert Counter(q["answer"] for q in outcome.items) == {"A": 2, "B": 2, "C": 2, "D": 2}


def test_verify_repair_repairs_flagged_candidates_and_reports_all_passed(catalog):
    evaluator = FakeEvaluator(first_flags=("weak:B", "weak:C"))
    outcome = verify_repair(make_job(strategy="verify_repair"), simulator_client(catalog), evaluator)
    assert len(outcome.items) == 3
    assert outcome.status == "all_passed"
    assert outcome.trace["candidates"] == 9 and outcome.trace["passed_before_repair"] == 0
    assert outcome.trace["repairs"][0]["accepted"] > 0
    assert outcome.usage.calls == 4  # 3 Writer calls + 1 repair


def test_verify_repair_fails_when_no_writer_call_succeeds(catalog):
    provider = ScriptedProvider([provider_error(503)] * 3)
    with pytest.raises(GenerationFailed):
        verify_repair(make_job(strategy="verify_repair"), client_for(catalog["simulator"], provider, 1), FakeEvaluator())


def test_selection_prefers_passing_questions_and_skips_near_duplicates():
    items = [_q("How does slow start grow the window?"), _q("How does slow start grow the window?"),
             _q("What triggers fast retransmit?"), _q("When does congestion avoidance begin?")]
    verdicts = [Verdict((), False, False, 9), Verdict((), False, False, 9),
                Verdict(("weak:B",), True, False, 5), Verdict(("off_topic",), False, True, 2)]
    assert select(items, verdicts, 2) == [0, 2]
    assert select(items, verdicts, 4) == [0, 2, 3, 1]
