"""
The comparison table: one row per model x strategy, the thesis framework applied to its questions.

As in the thesis there is no overall score, because the pillars trade off against each other. The table
is descriptive; the thesis tests differences by topic (Friedman, then Wilcoxon with Holm correction).
"""
import math
from collections import Counter, defaultdict
from typing import Optional

from .clients import Framework
from .models import Experiment, Item, Job
from .views import PILLAR_METRICS

GOOD = {"Better", "Best"}
LABELS = ("A", "B", "C", "D")


def _mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def _share(flags) -> Optional[float]:
    flags = [f for f in flags if f is not None]
    return round(sum(flags) / len(flags), 4) if flags else None


def chi2_sf_3(x: float) -> float:
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2)) + math.sqrt(2 * x / math.pi) * math.exp(-x / 2)


def key_checks(items: list[Item]) -> dict:
    n = len(items)
    counts = Counter(i.answer for i in items)
    positions = {label: counts.get(label, 0) for label in LABELS}
    if not n:
        return {"key_positions": positions, "key_position_p": None, "key_longest_rate": None}
    expected = n / 4
    chi2 = sum((c - expected) ** 2 / expected for c in positions.values())
    longest = sum(1 for i in items if all(len(i.options[i.answer]) > len(i.options[o]) for o in LABELS if o != i.answer))
    return {"key_positions": positions, "key_position_p": round(chi2_sf_3(chi2), 6),
            "key_longest_rate": round(longest / n, 4)}


def group_summary(items: list[Item], jobs: list[Job], framework: Optional[Framework]) -> dict:
    scored = [i for i in items if i.valid is not False]
    means = {metric: _mean(getattr(i, metric) for i in scored)
             for metric in ("alignment", "grade", "plausibility", "diversity", "alignment_lexical", "plausibility_lexical")}
    pillars = {}
    for key, metric in PILLAR_METRICS:
        entry = {"metric": metric, "mean": means[metric]}
        if framework is not None:
            entry["band_of_mean"] = framework.band(key, means[metric])
            if key == "P2":
                entry["share_in_zone"] = _share(framework.in_zone(key, i.grade) for i in scored)
            else:
                entry["share_better_or_best"] = _share(
                    None if getattr(i, metric) is None else framework.band(key, getattr(i, metric)) in GOOD for i in scored)
            if key == "P3a":
                entry["share_too_close"] = _share(
                    None if i.plausibility is None else framework.band(key, i.plausibility) == "Too close" for i in scored)
        pillars[key] = entry
    flag_counts = Counter(flag.split(":")[0] for i in scored for flag in (i.flags or []))
    return {
        "questions": len(items), "valid": sum(1 for i in items if i.valid), "means": means, "pillars": pillars,
        **key_checks(scored), "flags": dict(flag_counts.most_common()),
        "flags_checked": sum(1 for i in scored if i.flags is not None),
        "jobs": len(jobs), "failed_jobs": sum(1 for j in jobs if j.status == "failed"),
        "simulated": any(j.simulated for j in jobs),
        "cost_usd": round(sum(j.cost_usd for j in jobs), 6),
        "tokens": sum(j.prompt_tokens + j.completion_tokens for j in jobs),
        "mean_latency_seconds": _mean(j.latency_seconds for j in jobs),
    }


def _leaders(groups: list[dict]) -> dict:
    """The highest mean per pillar (P2: the largest share inside the target zone). Descriptive only."""
    leaders = {}
    for key, _ in PILLAR_METRICS:
        field = "share_in_zone" if key == "P2" else "mean"
        ranked = [g for g in groups if g["pillars"][key].get(field) is not None]
        if ranked:
            best = max(ranked, key=lambda g: g["pillars"][key][field])
            leaders[key] = {"model": best["model"], "strategy": best["strategy"], "value": best["pillars"][key][field]}
    return leaders


def experiment_summary(experiment: Experiment, framework: Optional[Framework]) -> dict:
    cells: dict[tuple, dict] = defaultdict(lambda: {"items": [], "jobs": []})
    for job in experiment.jobs:
        cell = cells[(job.model, job.strategy)]
        cell["jobs"].append(job)
        cell["items"] += job.items
    groups = [{"model": model, "strategy": strategy, **group_summary(cell["items"], cell["jobs"], framework)}
              for (model, strategy), cell in sorted(cells.items())]
    return {
        "experiment_id": experiment.id, "name": experiment.name, "origin": experiment.origin,
        "framework_version": framework.version if framework else None, "bands_available": framework is not None,
        "groups": groups, "leaders": _leaders(groups) if framework else {},
        "note": ("Descriptive comparison. No overall score: the pillars trade off against each other. "
                 "The thesis tests differences paired by topic (Friedman, Wilcoxon + Holm)."),
    }
