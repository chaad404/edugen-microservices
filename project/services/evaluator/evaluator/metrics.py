"""
Deterministic text metrics of the Three Pillars (ported from the thesis, src/evaluation/nlp_metrics.py).

The framework bands use the dense variants (all-MiniLM-L6-v2 embeddings). The lexical variants (TF cosine,
Jaccard) are kept for comparison with the thesis tables. Dense vectors are L2-normalised, so a dot product
is a cosine similarity.
"""
import math
import re
from collections import Counter
from typing import Sequence

import numpy as np
import textstat

_WORD = re.compile(r"\b\w+\b")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def lexical_alignment(source_text: str, stem: str) -> float:
    """P1, lexical: cosine between the term-frequency vectors of the source text and the stem."""
    if not source_text or not stem:
        return 0.0
    a, b = Counter(_tokens(source_text)), Counter(_tokens(stem))
    numerator = sum(a[t] * b[t] for t in a.keys() & b.keys())
    denominator = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return numerator / denominator if denominator else 0.0


def reading_grade(text: str) -> float:
    """P2: Flesch-Kincaid grade level of the stem. It describes wording, not content difficulty."""
    return float(textstat.flesch_kincaid_grade(text)) if text.strip() else 0.0


def lexical_plausibility(key_text: str, distractors: Sequence[str]) -> float:
    """P3a, lexical: mean Jaccard word overlap between the key and each distractor."""
    if not distractors:
        return 0.0
    key = set(_tokens(key_text))

    def jaccard(text: str) -> float:
        other = set(_tokens(text))
        union = key | other
        return len(key & other) / len(union) if union else 0.0

    return sum(jaccard(d) for d in distractors) / len(distractors)


def alignment_passages(source_text: str) -> list[str]:
    """The source passages a stem is compared with: paragraphs longer than 30 characters."""
    chunks = [p.strip() for p in source_text.split("\n\n") if len(p.strip()) > 30]
    return chunks or [source_text[:1000]]


def dense_alignment(stem: np.ndarray, passages: np.ndarray) -> float:
    """P1: maximum cosine between the stem and any source passage."""
    return float((passages @ stem).max())


def dense_plausibility(key: np.ndarray, distractors: np.ndarray) -> float:
    """P3a: mean cosine between the key and each distractor."""
    return float((distractors @ key).mean())


def dense_diversity(distractors: np.ndarray) -> float:
    """P3b: 1 - mean pairwise cosine among the distractors."""
    n = len(distractors)
    if n < 2:
        return 1.0
    sims = distractors @ distractors.T
    mean = sims[np.triu_indices(n, k=1)].mean()
    return max(0.0, 1.0 - float(mean))
