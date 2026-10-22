import math

import numpy as np
import pytest

from evaluator.metrics import (alignment_passages, dense_alignment, dense_diversity, dense_plausibility,
                               lexical_alignment, lexical_plausibility, reading_grade)


def test_lexical_alignment_is_a_term_frequency_cosine():
    assert lexical_alignment("tcp window", "tcp window") == pytest.approx(1.0)
    assert lexical_alignment("tcp window", "routing table") == 0.0
    # tf("a a b") = (2, 1), tf("a") = (1, 0): cosine = 2 / sqrt(5)
    assert lexical_alignment("a a b", "a") == pytest.approx(2 / math.sqrt(5))
    assert lexical_alignment("", "anything") == 0.0


def test_lexical_plausibility_is_the_mean_jaccard_overlap():
    # {fast retransmit} vs {fast recovery}: 1/3; vs {slow start}: 0
    assert lexical_plausibility("fast retransmit", ["fast recovery", "slow start"]) == pytest.approx(1 / 6)
    assert lexical_plausibility("key", []) == 0.0


def test_reading_grade_of_an_empty_stem_is_zero():
    assert reading_grade("   ") == 0.0
    long_stem = ("Which mechanism of the transmission control protocol retransmits a segment immediately after "
                 "three duplicate acknowledgements arrive, without waiting for the retransmission timeout?")
    assert reading_grade(long_stem) > 10


def test_alignment_passages_are_paragraphs_longer_than_30_characters():
    text = "Short.\n\nThis paragraph is clearly longer than thirty characters.\n\nAnother long enough paragraph here."
    assert alignment_passages(text) == ["This paragraph is clearly longer than thirty characters.",
                                        "Another long enough paragraph here."]
    assert alignment_passages("tiny") == ["tiny"]


def test_dense_metrics_on_known_vectors():
    x, y, z = np.eye(3, dtype=np.float32)
    assert dense_alignment(x, np.stack([y, x])) == pytest.approx(1.0)        # best passage counts
    assert dense_plausibility(x, np.stack([x, y])) == pytest.approx(0.5)
    assert dense_diversity(np.stack([x, y, z])) == pytest.approx(1.0)        # orthogonal distractors
    assert dense_diversity(np.stack([x, x, x])) == pytest.approx(0.0)        # three copies of one mistake
    assert dense_diversity(np.stack([x])) == 1.0
