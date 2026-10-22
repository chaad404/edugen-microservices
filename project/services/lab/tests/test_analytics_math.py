import pytest

from lab.analytics import _ranks, krippendorff_alpha, spearman


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
