import pytest

from evaluator.checks import (OptionGeometry, batch_checks, chi2_sf_3, evidence_in_context, is_serious,
                              item_flags, length_cue, quality_points)

OPTIONS = {"A": "the key option", "B": "first wrong one", "C": "second wrong one", "D": "third wrong one"}
NEUTRAL = OptionGeometry(to_key={"B": 0.5, "C": 0.5, "D": 0.5},
                         pairs={("B", "C"): 0.3, ("B", "D"): 0.3, ("C", "D"): 0.3})


def test_a_well_formed_item_has_no_flags():
    assert item_flags("A", OPTIONS, grade=12, alignment=0.75, geometry=NEUTRAL, diversity=0.7) == []


def test_distractor_flags_name_the_option_to_rewrite():
    geometry = OptionGeometry(to_key={"B": 0.85, "C": 0.2, "D": 0.5},
                              pairs={("B", "C"): 0.3, ("B", "D"): 0.9, ("C", "D"): 0.2})
    flags = item_flags("A", OPTIONS, grade=12, alignment=0.75, geometry=geometry, diversity=0.35)
    assert flags == ["too_close:B", "weak:C", "same_mistake:B,D"]


@pytest.mark.parametrize("grade,flag", [(6.5, "stem_too_simple"), (17.0, "stem_too_dense")])
def test_readability_flags(grade, flag):
    assert item_flags("A", OPTIONS, grade=grade) == [flag]


def test_off_topic_needs_an_alignment_value():
    assert item_flags("A", OPTIONS, grade=12, alignment=0.5) == ["off_topic"]
    assert item_flags("A", OPTIONS, grade=12, alignment=None) == []


def test_length_cue_when_the_key_is_clearly_the_longest():
    options = {"A": "a much longer correct answer than the rest", "B": "short", "C": "brief", "D": "tiny"}
    assert length_cue(options, "A")
    assert not length_cue(OPTIONS, "A")


def test_evidence_checks():
    context = "Three duplicate acknowledgements trigger fast retransmit of the missing segment."
    assert evidence_in_context("duplicate acknowledgements trigger fast retransmit", context)
    assert evidence_in_context("Three duplicate acknowledgements ... the missing segment", context)
    assert not evidence_in_context("a timeout always halves the window", context)

    flags = item_flags("A", OPTIONS, grade=12, evidence="a timeout always halves the window", context=context)
    assert flags == ["evidence_not_in_context"]

    rival = OptionGeometry(to_key=NEUTRAL.to_key, pairs=NEUTRAL.pairs,
                           to_evidence={"A": 0.6, "B": 0.7, "C": 0.1, "D": 0.1})
    flags = item_flags("A", OPTIONS, grade=12, geometry=rival, diversity=0.7,
                       evidence="duplicate acknowledgements trigger fast retransmit", context=context)
    assert flags == ["evidence_supports:B"]


def test_serious_flags_cannot_be_fixed_by_rewriting_options():
    assert is_serious(["off_topic"])
    assert is_serious(["invalid_schema"])
    assert not is_serious(["too_close:B", "length_cue"])


def test_quality_points_need_all_four_bands():
    assert quality_points({"P1": "Best", "P2": "Best", "P3a": "Better", "P3b": "Weak"}) == 8
    assert quality_points({"P1": None, "P2": "Best", "P3a": "Best", "P3b": "Best"}) is None


def test_chi_square_survival_with_three_degrees_of_freedom():
    assert chi2_sf_3(7.815) == pytest.approx(0.05, abs=5e-4)
    assert chi2_sf_3(0.0) == 1.0


def _item(answer, key_text="key"):
    options = {label: f"option {label}" for label in "ABCD"}
    options[answer] = key_text
    return {"question": f"Question about {answer} {key_text}?", "options": options, "answer": answer}


def test_batch_checks_detect_key_position_bias():
    balanced = [_item(label) for label in "ABCD" * 5]
    biased = [_item("A") for _ in range(20)]
    assert batch_checks(balanced)["key_position_p"] == pytest.approx(1.0)
    assert batch_checks(biased)["key_position_p"] < 0.001
    assert batch_checks(biased)["key_positions"] == {"A": 20, "B": 0, "C": 0, "D": 0}


def test_batch_checks_count_longest_keys_and_duplicate_stems():
    items = [_item("A", "the clearly longest key text"), _item("B", "k")]
    items.append(dict(items[0]))
    result = batch_checks(items)
    assert result["key_longest_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["duplicate_stems"] == 1
    assert batch_checks([])["key_position_p"] is None
