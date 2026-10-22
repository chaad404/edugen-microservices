"""
The quality framework of the thesis: four pillars, their frozen cut points and band labels.

Cut points for alignment, plausibility and diversity are the pooled quartiles of the April 2026 thesis baseline
(2,080 questions), frozen and applied unchanged to every later cohort. Readability uses US grade levels.
A value equal to a cut point belongs to the higher band.
"""
from bisect import bisect_right
from dataclasses import dataclass
from typing import Optional, Tuple

FRAMEWORK_VERSION = "thesis-2026-10"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(frozen=True)
class Pillar:
    key: str
    metric: str
    name: str
    question: str
    cuts: Tuple[float, ...]
    labels: Tuple[str, ...]
    # "higher": a higher value is better; "zone": the target is the interval in `zone`
    better: str = "higher"
    zone: Optional[Tuple[float, float]] = None
    warning: Optional[str] = None


PILLARS = (
    Pillar("P1", "alignment", "Semantic alignment",
           "Does the question stay on the topic's source material?",
           (0.64, 0.70, 0.76), ("Weak", "Good enough", "Better", "Best")),
    Pillar("P2", "grade", "Readability (Flesch-Kincaid grade)",
           "Is the question worded at a university reading level?",
           (8.0, 10.0, 14.0, 16.0), ("Too simple", "Good enough", "Best", "Good enough", "Too dense"),
           better="zone", zone=(10.0, 14.0)),
    Pillar("P3a", "plausibility", "Distractor plausibility",
           "Are the wrong options close enough to the key to be tempting?",
           (0.30, 0.45, 0.60, 0.80), ("Weak", "Good enough", "Better", "Best", "Too close"),
           warning="Too close"),
    Pillar("P3b", "diversity", "Distractor diversity",
           "Do the wrong options differ from each other?",
           (0.40, 0.55, 0.70), ("Weak", "Good enough", "Better", "Best")),
)
BY_KEY = {p.key: p for p in PILLARS}

# Points per band, used to rank candidate questions (a question in every Best band scores 12)
POINTS = {"Weak": 0, "Good enough": 1, "Better": 2, "Best": 3, "Too close": 0, "Too simple": 0, "Too dense": 0}


def band(pillar: Pillar, value: float) -> str:
    return pillar.labels[bisect_right(pillar.cuts, value)]


def describe() -> dict:
    """The framework as data, so other services apply the same cut points without copying them."""
    return {
        "version": FRAMEWORK_VERSION,
        "embedding_model": EMBEDDING_MODEL,
        "pillars": [
            {"key": p.key, "metric": p.metric, "name": p.name, "question": p.question,
             "cuts": list(p.cuts), "labels": list(p.labels), "better": p.better,
             "zone": list(p.zone) if p.zone else None, "warning": p.warning}
            for p in PILLARS
        ],
        "points": POINTS,
    }
