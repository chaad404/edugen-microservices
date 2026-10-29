"""
Generation strategies, one per thesis condition (thesis docs/pipeline_v2.md):

- baseline:      the April 2026 zero-shot template, topic text only, one call
- prompt_v2:     prompt v2, one call, then the options are re-ordered so the keys are spread over A-D
- verify_repair: Writer (3 focused prompt-v2 calls) -> Evaluator checks -> Repairer (LLM, only the flagged
                 options, at most 2 rounds) -> Selector (code) -> key balancing. This is the thesis's
                 multi-agent v2 without course-material retrieval (the course PDFs are not part of this project).

Every strategy records the key letters as the model wrote them (`raw_answers` in the trace) before any
re-ordering, as the thesis does, so a model's key-position bias stays measurable after the keys are balanced.
"""
import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from . import prompts
from .evaluator_client import Verdict
from .llm import GenerationFailed, Usage
from .validation import InvalidOutput, normalize_mcq, normalized_questions, validate_single_mcq

LABELS = ("A", "B", "C", "D")
WRITER_CALLS = 3
REPAIR_ROUNDS = 2
REPAIR_BATCH = 8
MAX_STEM_OVERLAP = 0.8

DESCRIPTIONS = {
    "baseline": "Thesis April 2026 zero-shot template: topic text only, one call.",
    "prompt_v2": "Thesis prompt v2 (evidence quote, item-writing rules), one call, keys balanced over A-D.",
    "verify_repair": "Writer (3 calls) -> Evaluator checks -> targeted LLM repair (max 2 rounds) -> selection.",
}


@dataclass(frozen=True)
class Job:
    job_id: str
    experiment_id: str
    topic_id: str
    topic_title: str
    domain: str
    source_text: str
    model: str
    strategy: str
    num_questions: int


@dataclass
class Outcome:
    items: list
    usage: Usage
    attempts: int
    returned_model_id: Optional[str]
    status: str
    trace: dict = field(default_factory=dict)


# --- Key balancing (ported from the thesis pipeline v2) ---

def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def balanced_positions(n: int, rng: random.Random) -> list[str]:
    """Key positions for n questions: every letter used equally often (up to one extra), in random order."""
    positions = []
    while len(positions) < n:
        block = list(LABELS)
        rng.shuffle(block)
        positions += block
    positions = positions[:n]
    rng.shuffle(positions)
    return positions


def shuffle_options(item: dict, target: str, rng: random.Random) -> dict:
    """Moves the key to `target`; the distractors fill the other letters in random order."""
    key_text = item["options"][item["answer"]]
    distractors = [item["options"][label] for label in LABELS if label != item["answer"]]
    rng.shuffle(distractors)
    others = iter(distractors)
    return {**item, "options": {label: key_text if label == target else next(others) for label in LABELS},
            "answer": target}


def shuffle_batch(questions: Sequence[dict], *seed_parts) -> list[dict]:
    """Deterministic for the same topic/model/strategy, so a rerun reproduces the stored order."""
    rng = random.Random(_seed(*seed_parts))
    return [shuffle_options(q, t, rng) for q, t in zip(questions, balanced_positions(len(questions), rng))]


# --- Strategies ---

def _letters(items: Sequence[dict]) -> list[str]:
    return [q["answer"] for q in items]


def _expect(n: int):
    return lambda data: normalized_questions(data, n)


def baseline(job: Job, llm, evaluator=None) -> Outcome:
    items, usage, attempts, returned = llm.complete_json(prompts.v1_messages(job.source_text, job.num_questions),
                                                         _expect(job.num_questions))
    return Outcome(items, usage, attempts, returned, "valid", {"raw_answers": _letters(items)})


def prompt_v2(job: Job, llm, evaluator=None) -> Outcome:
    items, usage, attempts, returned = llm.complete_json(prompts.v2_messages(job.source_text, job.num_questions),
                                                         _expect(job.num_questions))
    return Outcome(shuffle_batch(items, job.topic_id, job.model, "prompt_v2"), usage, attempts, returned, "valid",
                   {"key_balance": "shuffled", "raw_answers": _letters(items)})


def _stem_overlap(a: dict, b: dict) -> float:
    wa, wb = (set(re.findall(r"[a-z0-9]+", q["question"].lower())) for q in (a, b))
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


def select(items: Sequence[dict], verdicts: Sequence[Verdict], n: int) -> list[int]:
    """
    Picks n questions: those that pass every check first, then those without serious flags, then by fewest
    flags; higher pillar quality breaks ties. A stem too similar to one already picked is skipped while
    alternatives remain. (The thesis compares stem embeddings; word overlap avoids another Evaluator call.)
    """
    order = sorted(range(len(items)), key=lambda i: (verdicts[i].serious, len(verdicts[i].flags), -(verdicts[i].quality or 0)))
    chosen = []
    for i in order:
        if all(_stem_overlap(items[i], items[j]) < MAX_STEM_OVERLAP for j in chosen):
            chosen.append(i)
        if len(chosen) == n:
            return chosen
    for i in order:  # not enough distinct stems: fill with the best remaining
        if i not in chosen:
            chosen.append(i)
        if len(chosen) == n:
            break
    return chosen


def _revised(data: dict, count: int) -> list[Optional[dict]]:
    """Repairer output: one valid question or None per question sent; a wrong count rejects them all."""
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise InvalidOutput("Repair output is missing the 'questions' array.")
    if len(questions) != count:
        return [None] * count
    out = []
    for raw in questions:
        item = normalize_mcq(raw)
        if validate_single_mcq(item)[0]:
            clean = {"question": str(item["question"]).strip(),
                     "options": {label: str(item["options"][label]).strip() for label in LABELS},
                     "answer": item["answer"]}
            if item.get("evidence"):
                clean["evidence"] = str(item["evidence"]).strip()
            out.append(clean)
        else:
            out.append(None)
    return out


def verify_repair(job: Job, llm, evaluator) -> Outcome:
    usage, trace = Usage(), {"writer": [], "repairs": []}
    candidates, attempts, returned = [], 0, None
    for focus in prompts.focus_groups(job.source_text, WRITER_CALLS):
        try:
            items, u, a, r = llm.complete_json(prompts.v2_messages(job.source_text, job.num_questions, focus),
                                               _expect(job.num_questions))
        except GenerationFailed as e:  # one failed Writer call still leaves the others' candidates
            usage.merge(e.usage)
            trace["writer"].append({"focus": focus, "outcome": "failed"})
            continue
        usage.merge(u)
        attempts, returned = max(attempts, a), returned or r
        candidates += items
        trace["writer"].append({"focus": focus, "outcome": "ok", "attempts": a})
    if len(candidates) < job.num_questions:
        raise GenerationFailed("invalid_output", f"Writer produced {len(candidates)} valid questions, "
                               f"fewer than {job.num_questions}", attempts or llm.max_attempts, usage)

    verdicts = evaluator.check(job.source_text, candidates)
    trace["candidates"] = len(candidates)
    trace["passed_before_repair"] = sum(v.passed for v in verdicts)

    for round_no in range(1, REPAIR_ROUNDS + 1):
        # Repair the most promising flagged candidates: the ones the Selector would reach first
        picked = set(select(candidates, verdicts, job.num_questions))
        todo = [i for i in sorted(range(len(candidates)), key=lambda i: (i not in picked, len(verdicts[i].flags)))
                if verdicts[i].repairable][:REPAIR_BATCH]
        if not todo or all(verdicts[i].passed for i in picked):
            break
        messages = prompts.repair_messages(job.source_text, [candidates[i] for i in todo], [verdicts[i].flags for i in todo])
        try:
            revised, u, _, _ = llm.complete_json(messages, lambda data: _revised(data, len(todo)))
        except GenerationFailed as e:
            usage.merge(e.usage)
            trace["repairs"].append({"round": round_no, "outcome": "failed"})
            break
        usage.merge(u)
        valid = [(i, item) for i, item in zip(todo, revised) if item is not None]
        new_verdicts = evaluator.check(job.source_text, [item for _, item in valid]) if valid else []
        accepted = 0
        for (i, item), verdict in zip(valid, new_verdicts):
            # A repair is kept only if it leaves fewer flags and no serious one
            if not verdict.serious and len(verdict.flags) < len(verdicts[i].flags):
                candidates[i], verdicts[i] = item, verdict
                accepted += 1
        trace["repairs"].append({"round": round_no, "attempted": len(todo), "valid": len(valid), "accepted": accepted})

    chosen = select(candidates, verdicts, job.num_questions)
    picked = [candidates[i] for i in chosen]
    trace["key_balance"], trace["raw_answers"] = "shuffled", _letters(picked)
    final = shuffle_batch(picked, job.topic_id, job.model, "verify_repair")
    trace["selected_passing_all_checks"] = sum(verdicts[i].passed for i in chosen)
    status = "all_passed" if all(verdicts[i].passed for i in chosen) else "best_effort"
    return Outcome(final, usage, attempts, returned, status, trace)


STRATEGIES = {"baseline": baseline, "prompt_v2": prompt_v2, "verify_repair": verify_repair}
