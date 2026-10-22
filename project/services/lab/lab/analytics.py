"""
Human versus automatic evaluation of a study (thesis experiment protocol, section 6):
inter-rater agreement (Krippendorff's alpha, ported from the thesis), Spearman correlations between the
human judgements and the automatic pillars, and classic item analysis of the student answers.
"""
from collections import Counter, defaultdict
from typing import Optional, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import HumanRating, QuizAnswer, QuizFeedback, Study
from .views import study_view

DIMENSIONS = ("relevance", "clarity", "difficulty", "distractors")
LABELS = ("A", "B", "C", "D")
AUTOMATIC = ("alignment", "grade", "plausibility", "diversity")
# (human judgement, automatic metric): what the thesis expects each pillar to approximate
CORRELATIONS = (("expert_relevance", "alignment"), ("expert_distractors", "plausibility"),
                ("expert_distractors", "diversity"), ("expert_difficulty", "grade"),
                ("student_p_value", "plausibility"), ("student_perceived_difficulty", "grade"))
MIN_PAIRS = 5


def krippendorff_alpha(reliability_data: Sequence[Sequence[Optional[float]]], level: str = "ordinal") -> Optional[float]:
    """
    Krippendorff's alpha for a raters x units matrix (None = missing). Units rated by fewer than two raters are
    ignored. Reference: Krippendorff (2011), "Computing Krippendorff's Alpha-Reliability".
    """
    units = list(zip(*reliability_data))
    values = sorted({v for unit in units for v in unit if v is not None})
    if len(values) < 2:
        return None
    index = {v: i for i, v in enumerate(values)}
    coincidence = np.zeros((len(values), len(values)))
    for unit in units:
        rated = [v for v in unit if v is not None]
        m = len(rated)
        if m < 2:
            continue
        for i, a in enumerate(rated):
            for j, b in enumerate(rated):
                if i != j:
                    coincidence[index[a], index[b]] += 1.0 / (m - 1)
    n_c = coincidence.sum(axis=1)
    n = n_c.sum()
    if n < 2:
        return None
    k = len(values)
    delta = np.zeros((k, k))
    for c in range(k):
        for d in range(k):
            if level == "nominal":
                delta[c, d] = 0.0 if c == d else 1.0
            elif level == "ordinal":
                lo, hi = min(c, d), max(c, d)
                delta[c, d] = (n_c[lo:hi + 1].sum() - (n_c[c] + n_c[d]) / 2.0) ** 2
            else:
                delta[c, d] = (values[c] - values[d]) ** 2
    observed = (coincidence * delta).sum() / n
    expected = (np.outer(n_c, n_c) * delta).sum() / (n * (n - 1))
    return round(float(1.0 - observed / expected), 4) if expected > 0 else None


def _ranks(values: Sequence[float]) -> np.ndarray:
    """Ranks starting at 1; ties get their average rank."""
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array))
    i = 0
    while i < len(array):
        j = i
        while j + 1 < len(array) and array[order[j + 1]] == array[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < MIN_PAIRS:
        return None
    rx, ry = _ranks(x), _ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return round(float(np.corrcoef(rx, ry)[0, 1]), 4)


def _mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(float(np.mean(values)), 4) if values else None


def _key_rate(ratings) -> Optional[float]:
    decided = [r.key_correct for r in ratings if r.key_correct in ("yes", "no")]
    return round(decided.count("yes") / len(decided), 4) if decided else None


def study_analytics(session: Session, study: Study) -> dict:
    ratings = list(session.scalars(select(HumanRating).where(HumanRating.study_id == study.id)))
    answers = list(session.scalars(select(QuizAnswer).where(QuizAnswer.study_id == study.id)))
    feedback = list(session.scalars(select(QuizFeedback).where(QuizFeedback.study_id == study.id)))
    by_ref = {name: defaultdict(list) for name in ("ratings", "answers", "feedback")}
    for r in ratings:
        by_ref["ratings"][r.item_ref].append(r)
    for a in answers:
        by_ref["answers"][a.item_ref].append(a)
    for f in feedback:
        by_ref["feedback"][f.item_ref].append(f)

    items = []
    for si in study.items:
        item, job = si.item, si.item.job
        r, a, f = by_ref["ratings"][si.item_ref], by_ref["answers"][si.item_ref], by_ref["feedback"][si.item_ref]
        picks = Counter(x.chosen for x in a)
        items.append({
            "item_ref": si.item_ref, "item_id": item.id, "model": job.model, "strategy": job.strategy,
            "domain": job.topic.domain, "topic_id": job.topic.topic_id, "question": item.question,
            "answer": item.answer, "automatic": {m: getattr(item, m) for m in AUTOMATIC},
            "expert": {"ratings": len(r), **{d: _mean(getattr(x, d) for x in r) for d in DIMENSIONS},
                       "key_correct_rate": _key_rate(r), "unusable": sum(1 for x in r if x.unusable),
                       "comments": [x.comment for x in r if x.comment]},
            "student": {"attempts": len(a), "p_value": _mean(1.0 if x.correct else 0.0 for x in a),
                        "mean_time_ms": _mean(x.time_ms for x in a),
                        "option_counts": {label: picks.get(label, 0) for label in LABELS},
                        # a distractor nobody picks does not work; only meaningful with a few attempts
                        "dead_distractors": [label for label in LABELS if label != item.answer and not picks.get(label)]
                        if len(a) >= 3 else [],
                        "clarity": _mean(x.clarity for x in f), "helpfulness": _mean(x.helpfulness for x in f),
                        "perceived_difficulty": _mean(x.difficulty for x in f)},
        })

    groups = defaultdict(list)
    for entry in items:
        groups[(entry["model"], entry["strategy"])].append(entry)
    group_rows = []
    for (model, strategy), entries in sorted(groups.items()):
        refs = {e["item_ref"] for e in entries}
        group_ratings = [r for r in ratings if r.item_ref in refs]
        group_answers = [a for a in answers if a.item_ref in refs]
        group_feedback = [f for f in feedback if f.item_ref in refs]
        group_rows.append({
            "model": model, "strategy": strategy, "items": len(entries),
            "automatic": {m: _mean(e["automatic"][m] for e in entries) for m in AUTOMATIC},
            "expert": {"ratings": len(group_ratings), **{d: _mean(getattr(r, d) for r in group_ratings) for d in DIMENSIONS},
                       "key_correct_rate": _key_rate(group_ratings),
                       "unusable_rate": _mean(1.0 if r.unusable else 0.0 for r in group_ratings)},
            "student": {"answers": len(group_answers), "p_value": _mean(1.0 if a.correct else 0.0 for a in group_answers),
                        "mean_time_ms": _mean(a.time_ms for a in group_answers),
                        "clarity": _mean(f.clarity for f in group_feedback),
                        "helpfulness": _mean(f.helpfulness for f in group_feedback),
                        "perceived_difficulty": _mean(f.difficulty for f in group_feedback)},
        })

    raters = sorted({r.rater for r in ratings})
    refs = [si.item_ref for si in study.items]
    multi = [ref for ref in refs if len({r.rater for r in by_ref["ratings"][ref]}) >= 2]
    agreement = {}
    for dimension in DIMENSIONS + ("key_correct",):
        matrix = []
        for rater in raters:
            row = []
            for ref in multi:
                mine = next((r for r in by_ref["ratings"][ref] if r.rater == rater), None)
                if mine is None:
                    row.append(None)
                elif dimension == "key_correct":
                    row.append({"yes": 1, "no": 0}.get(mine.key_correct))
                else:
                    row.append(getattr(mine, dimension))
            matrix.append(row)
        level = "nominal" if dimension == "key_correct" else "ordinal"
        agreement[dimension] = {"level": level, "raters": len(raters), "items_with_2_raters": len(multi),
                                "alpha": krippendorff_alpha(matrix, level) if len(raters) >= 2 and multi else None}

    def human(entry, name):
        source, field = name.split("_", 1)
        return entry[source][field]

    correlations = []
    for human_name, metric in CORRELATIONS:
        pairs = [(human(e, human_name), e["automatic"][metric]) for e in items
                 if human(e, human_name) is not None and e["automatic"][metric] is not None]
        correlations.append({"human": human_name, "metric": metric, "n": len(pairs),
                             "spearman_rho": spearman([p[0] for p in pairs], [p[1] for p in pairs])})

    return {
        "study": study_view(study),
        "progress": {"raters": len(raters), "ratings": len(ratings), "participants": len({a.participant for a in answers}),
                     "answers": len(answers), "feedback": len(feedback)},
        "groups": group_rows, "agreement": agreement, "correlations": correlations, "items": items,
        "note": f"Correlations need at least {MIN_PAIRS} items with both values; agreement needs two raters per item.",
    }
