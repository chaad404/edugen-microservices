"""
Item-writing checks for one question and for a batch (ported from the thesis verifier,
src/generation/verifier.py, and the batch checks in docs/baseline_framework.md section 5).

Flags are "code" or "code:A[,B]" strings, so a repair step knows which option to rewrite and why.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional, Sequence

from .framework import BY_KEY, POINTS

LABELS = ("A", "B", "C", "D")
OFF_TOPIC = BY_KEY["P1"].cuts[0]             # 0.64
STEM_TOO_SIMPLE = BY_KEY["P2"].cuts[0]       # grade 8
STEM_TOO_DENSE = BY_KEY["P2"].cuts[-1]       # grade 16
WEAK_DISTRACTOR = BY_KEY["P3a"].cuts[0]      # 0.30: unrelated to the key, easy to rule out
TOO_CLOSE = BY_KEY["P3a"].cuts[-1]           # 0.80: nearly the key itself
LOW_DIVERSITY = BY_KEY["P3b"].cuts[0]        # 0.40
LENGTH_CUE_RATIO = 1.2
EVIDENCE_NGRAM = 5
EVIDENCE_COVERAGE = 0.6

# Flags that rewriting the options or the stem can fix; the others need a different question
REPAIRABLE = {"too_close", "weak", "same_mistake", "length_cue", "evidence_supports",
              "stem_too_simple", "stem_too_dense"}


@dataclass(frozen=True)
class OptionGeometry:
    """Dense similarities between the options of one question."""
    to_key: dict                         # distractor label -> cosine with the key
    pairs: dict                          # (label, label) of two distractors -> cosine
    to_evidence: Optional[dict] = None   # label -> cosine with the quoted evidence


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def evidence_in_context(evidence: str, context: str) -> bool:
    """The quoted evidence (possibly several fragments joined by '...') must appear in the context."""
    words = _words(context)
    joined = " ".join(words)
    fragments = [f for f in re.split(r"\.\.\.|…", evidence or "") if len(_words(f)) >= 3]
    if not fragments:
        return False
    grams = {tuple(words[i:i + EVIDENCE_NGRAM]) for i in range(len(words) - EVIDENCE_NGRAM + 1)}
    for fragment in fragments:
        f_words = _words(fragment)
        if " ".join(f_words) in joined:
            continue
        f_grams = [tuple(f_words[i:i + EVIDENCE_NGRAM]) for i in range(len(f_words) - EVIDENCE_NGRAM + 1)]
        if not f_grams or sum(g in grams for g in f_grams) / len(f_grams) < EVIDENCE_COVERAGE:
            return False
    return True


def length_cue(options: dict, answer: str) -> bool:
    """The key is the longest option and clearly longer than the mean distractor."""
    lengths = {label: len(options[label]) for label in LABELS}
    others = [lengths[label] for label in LABELS if label != answer]
    return lengths[answer] == max(lengths.values()) and lengths[answer] > LENGTH_CUE_RATIO * sum(others) / len(others)


def item_flags(answer: str, options: dict, grade: float, alignment: Optional[float] = None,
               geometry: Optional[OptionGeometry] = None, diversity: Optional[float] = None,
               evidence: Optional[str] = None, context: Optional[str] = None) -> list[str]:
    """
    Flags for one valid question. Checks that need a missing input are skipped, never guessed:
    alignment needs the source text, the option checks need embeddings, the evidence checks need both
    a quoted evidence and a context.
    """
    flags = []
    if alignment is not None and alignment < OFF_TOPIC:
        flags.append("off_topic")
    if grade < STEM_TOO_SIMPLE:
        flags.append("stem_too_simple")
    elif grade > STEM_TOO_DENSE:
        flags.append("stem_too_dense")
    if geometry is not None:
        flags += [f"too_close:{label}" for label, s in geometry.to_key.items() if s >= TOO_CLOSE]
        flags += [f"weak:{label}" for label, s in geometry.to_key.items() if s < WEAK_DISTRACTOR]
        if diversity is not None and diversity < LOW_DIVERSITY:
            a, b = max(geometry.pairs, key=geometry.pairs.get)
            flags.append(f"same_mistake:{a},{b}")
    if length_cue(options, answer):
        flags.append("length_cue")
    if evidence and context:
        if not evidence_in_context(evidence, context):
            flags.append("evidence_not_in_context")
        elif geometry is not None and geometry.to_evidence:
            e = geometry.to_evidence
            rivals = [label for label in LABELS if label != answer and e[label] >= e[answer]]
            if rivals:
                flags.append("evidence_supports:" + ",".join(rivals))
    return flags


def is_serious(flags: Sequence[str]) -> bool:
    """A flag that rewriting options cannot fix (off topic, evidence not found, invalid schema)."""
    return any(flag.split(":")[0] not in REPAIRABLE for flag in flags)


def quality_points(bands: dict) -> Optional[int]:
    """Sum of band points over the four pillars; None if a pillar could not be measured."""
    if any(value is None for value in bands.values()):
        return None
    return sum(POINTS[value] for value in bands.values())


def chi2_sf_3(x: float) -> float:
    """Survival function of the chi-square distribution with 3 degrees of freedom."""
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2)) + math.sqrt(2 * x / math.pi) * math.exp(-x / 2)


def batch_checks(items: Sequence[dict]) -> dict:
    """Key-position balance (chi-square against 25% each), longest-option cue and duplicate stems."""
    n = len(items)
    counts = Counter(item["answer"] for item in items)
    positions = {label: counts.get(label, 0) for label in LABELS}
    if not n:
        return {"n": 0, "key_positions": positions, "key_position_chi2": None, "key_position_p": None,
                "key_longest_rate": None, "duplicate_stems": 0}
    expected = n / 4
    chi2 = sum((count - expected) ** 2 / expected for count in positions.values())
    longest = sum(
        1 for item in items
        if all(len(item["options"][item["answer"]]) > len(item["options"][label]) for label in LABELS if label != item["answer"])
    )
    stems = [" ".join(_words(item["question"])) for item in items]
    return {"n": n, "key_positions": positions, "key_position_chi2": round(chi2, 4),
            "key_position_p": round(chi2_sf_3(chi2), 6), "key_longest_rate": round(longest / n, 4),
            "duplicate_stems": len(stems) - len(set(stems))}
