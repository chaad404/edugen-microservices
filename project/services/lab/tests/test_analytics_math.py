from collections import Counter

import pytest

from lab.analytics import _ranks, difficulty_note, krippendorff_alpha, spearman, unused_options
from lab.summaries import _leaders


def test_perfect_agreement_is_one():
    assert krippendorff_alpha([[1, 2, 3, 4], [1, 2, 3, 4]], "ordinal") == pytest.approx(1.0)


def test_krippendorff_reference_example_nominal():
    # Krippendorff (2011), "Computing Krippendorff's Alpha-Reliability", nominal example: alpha = 0.743
    a = [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None]
    b = [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3]
    c = [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None]
    d = [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None]
    assert krippendorff_alpha([a, b, c, d], "nominal") == pytest.approx(0.743, abs=1e-3)


def test_alpha_needs_two_values_and_two_ratings_per_unit():
    assert krippendorff_alpha([[3, 3], [3, 3]], "ordinal") is None
    assert krippendorff_alpha([[1, None], [None, 2]], "ordinal") is None


def test_ranks_average_ties():
    assert list(_ranks([10, 20, 20, 30])) == [1.0, 2.5, 2.5, 4.0]


def test_spearman():
    assert spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 2, 3], [1, 2, 3]) is None          # too few pairs
    assert spearman([1, 1, 1, 1, 1], [1, 2, 3, 4, 5]) is None  # no variation


def test_a_question_is_judged_too_hard_or_too_easy_only_with_enough_answers():
    assert difficulty_note(0.0, 2) is None           # two answers say nothing yet
    assert difficulty_note(None, 5) is None
    assert difficulty_note(0.1, 10) == "too_hard"
    assert difficulty_note(1.0, 3) == "too_easy"
    assert difficulty_note(0.2, 5) is None and difficulty_note(0.9, 10) is None  # the limits belong to the normal range


def test_an_option_is_called_unused_only_after_enough_answers():
    assert unused_options(Counter({"A": 3}), "A", 3) == []  # three answers leave options unchosen by chance alone
    assert unused_options(Counter({"A": 12, "B": 8}), "A", 20) == ["C", "D"]
    assert unused_options(Counter({"B": 20}), "A", 20) == ["C", "D"]  # the key is never reported as a distractor
    assert unused_options(Counter({"A": 5, "B": 5, "C": 5, "D": 5}), "A", 20) == []


def test_a_group_that_lost_jobs_does_not_lead_a_pillar():
    def group(model, mean, failed_jobs):
        pillars = {key: {"mean": mean, "share_in_zone": mean} for key in ("P1", "P2", "P3a", "P3b")}
        return {"model": model, "strategy": "baseline", "failed_jobs": failed_jobs, "pillars": pillars}

    leaders = _leaders([group("complete", 0.70, 0), group("partial", 0.75, 2)])
    assert {leader["model"] for leader in leaders.values()} == {"complete"}  # fewer topics: not comparable
    assert _leaders([group("partial", 0.75, 2)])["P1"]["model"] == "partial"  # nothing better to rank
