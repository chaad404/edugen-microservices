"""Scores a batch of questions: metrics, bands and flags per question, plus the batch checks."""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .checks import LABELS, OptionGeometry, batch_checks, is_serious, item_flags, quality_points
from .embedder import Embedder
from .framework import BY_KEY, FRAMEWORK_VERSION, band
from .metrics import (alignment_passages, dense_alignment, dense_diversity, dense_plausibility,
                      lexical_alignment, lexical_plausibility, reading_grade)
from .schemas import Bands, BatchResult, EvaluationRequest, EvaluationResponse, ItemResult, Metrics
from .validation import normalize_mcq, validate_single_mcq


@dataclass
class _Vectors:
    stem: np.ndarray
    options: dict
    evidence: Optional[np.ndarray]


def _embed(embedder: Embedder, source: Optional[str], items: list[dict]):
    """One embedding call for all passages, stems, options and evidence quotes of the request."""
    passages = alignment_passages(source) if source else []
    texts = list(passages)
    for item in items:
        texts.append(item["question"])
        texts += [item["options"][label] for label in LABELS]
        if item.get("evidence"):
            texts.append(item["evidence"])
    matrix = embedder.embed(texts)

    passage_vectors = matrix[:len(passages)] if passages else None
    cursor, per_item = len(passages), []
    for item in items:
        stem, options = matrix[cursor], dict(zip(LABELS, matrix[cursor + 1:cursor + 5]))
        cursor += 5
        evidence = None
        if item.get("evidence"):
            evidence, cursor = matrix[cursor], cursor + 1
        per_item.append(_Vectors(stem, options, evidence))
    return passage_vectors, per_item


def _r(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 4)


def _score(item_id, item: dict, source: Optional[str], context: Optional[str],
           passages: Optional[np.ndarray], vectors: Optional[_Vectors]) -> ItemResult:
    stem, options, answer = item["question"], item["options"], item["answer"]
    others = [label for label in LABELS if label != answer]
    grade = reading_grade(stem)
    alignment = plausibility = diversity = geometry = None
    if vectors is not None:
        if passages is not None:
            alignment = dense_alignment(vectors.stem, passages)
        distractors = np.stack([vectors.options[label] for label in others])
        plausibility = dense_plausibility(vectors.options[answer], distractors)
        diversity = dense_diversity(distractors)
        key = vectors.options[answer]
        to_evidence = None
        if vectors.evidence is not None:
            to_evidence = {label: float(vectors.evidence @ vectors.options[label]) for label in LABELS}
        geometry = OptionGeometry(
            to_key={label: float(vectors.options[label] @ key) for label in others},
            pairs={(a, b): float(vectors.options[a] @ vectors.options[b]) for i, a in enumerate(others) for b in others[i + 1:]},
            to_evidence=to_evidence,
        )

    flags = item_flags(answer, options, grade, alignment, geometry, diversity, item.get("evidence"), context)
    bands = {
        "P1": band(BY_KEY["P1"], alignment) if alignment is not None else None,
        "P2": band(BY_KEY["P2"], grade),
        "P3a": band(BY_KEY["P3a"], plausibility) if plausibility is not None else None,
        "P3b": band(BY_KEY["P3b"], diversity) if diversity is not None else None,
    }
    serious = is_serious(flags)
    return ItemResult(
        id=item_id, valid=True, validation_notes="Valid",
        metrics=Metrics(
            alignment=_r(alignment),
            alignment_lexical=_r(lexical_alignment(source, stem)) if source else None,
            grade=_r(grade),
            plausibility=_r(plausibility),
            plausibility_lexical=_r(lexical_plausibility(options[answer], [options[label] for label in others])),
            diversity=_r(diversity),
        ),
        bands=Bands(**bands), flags=flags, repairable=bool(flags) and not serious, serious=serious,
        quality=quality_points(bands),
    )


def evaluate(request: EvaluationRequest, embedder: Optional[Embedder]) -> EvaluationResponse:
    source = request.source_text or None
    context = request.context or source
    prepared = []
    for item in request.items:
        raw = normalize_mcq(item.model_dump(exclude={"id"}, exclude_none=True))
        ok, notes = validate_single_mcq(raw)
        prepared.append((item.id, raw, ok, notes))

    valid = [raw for _, raw, ok, _ in prepared if ok]
    passages, vectors = _embed(embedder, source, valid) if embedder is not None and valid else (None, [])
    vector_iter = iter(vectors)

    results = []
    for item_id, raw, ok, notes in prepared:
        if not ok:
            results.append(ItemResult(id=item_id, valid=False, validation_notes=notes, metrics=Metrics(),
                                      bands=Bands(), flags=["invalid_schema"], repairable=False, serious=True))
            continue
        results.append(_score(item_id, raw, source, context, passages, next(vector_iter, None)))

    return EvaluationResponse(
        framework_version=FRAMEWORK_VERSION,
        dense_available=embedder is not None,
        embedding_model=embedder.model_name if embedder is not None else None,
        items=results,
        batch=BatchResult(**batch_checks(valid)),
    )
