from evaluator.validation import normalize_mcq, validate_single_mcq

GOOD = {"question": "Which layer routes packets between networks?",
        "options": {"A": "Network layer", "B": "Data link layer", "C": "Transport layer", "D": "Session layer"},
        "answer": "A"}


def test_normalize_maps_other_shapes_onto_the_canonical_one():
    item = normalize_mcq({"question_stem": "Q?", "options": ["w", "x", "y", "z"], "correct_answer": "b)"})
    assert item == {"question": "Q?", "options": {"A": "w", "B": "x", "C": "y", "D": "z"}, "answer": "B"}


def test_the_exact_option_text_is_accepted_as_the_answer():
    item = normalize_mcq({**GOOD, "answer": "Transport layer"})
    assert item["answer"] == "C"


def test_validation_accepts_a_good_item():
    assert validate_single_mcq(GOOD) == (True, "Valid")


def test_validation_rejects_common_defects():
    assert not validate_single_mcq({**GOOD, "options": {**GOOD["options"], "D": "network layer"}})[0]
    assert not validate_single_mcq({**GOOD, "question": "Based on the context, which layer routes?"})[0]
    assert not validate_single_mcq({**GOOD, "question": "Routing?"})[0]
    assert not validate_single_mcq({**GOOD, "answer": "E"})[0]
    missing = {k: v for k, v in GOOD.items() if k != "answer"}
    assert validate_single_mcq(missing) == (False, "Missing required key: answer")
