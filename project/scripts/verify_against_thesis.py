"""
Checks that the Evaluator service reproduces the scores stored by the thesis, on real thesis questions.

The thesis database is opened read-only; nothing is written. The embedding model is downloaded once into
the given cache folder.

    python verify_against_thesis.py <thesis app.db> <model cache folder> [number of questions]
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "evaluator"))

from evaluator.embedder import FastEmbedEmbedder  # noqa: E402
from evaluator.schemas import EvaluationRequest  # noqa: E402
from evaluator.service import evaluate  # noqa: E402

QUERY = """
SELECT t.source_text, q.question_stem, q.option_a, q.option_b, q.option_c, q.option_d, q.correct_option,
       e.score_dense_semantic_alignment, e.score_linguistic_complexity, e.score_dense_distractor_plausibility,
       e.score_distractor_diversity, e.score_semantic_alignment, e.score_distractor_plausibility
FROM generated_questions q
JOIN generation_runs r ON q.run_fk = r.id
JOIN topics t ON r.topic_fk = t.id
JOIN evaluation_results e ON e.question_fk = q.id
WHERE e.score_dense_semantic_alignment IS NOT NULL AND r.is_simulated = 0
ORDER BY q.id
"""
METRICS = ("alignment", "grade", "plausibility", "diversity", "alignment_lexical", "plausibility_lexical")


def main() -> None:
    database, cache = sys.argv[1], sys.argv[2]
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    rows = sqlite3.connect(f"file:{database}?mode=ro&immutable=1", uri=True).execute(QUERY).fetchall()
    sample = rows[::max(1, len(rows) // count)][:count]  # spread over all batches, models and topics

    embedder = FastEmbedEmbedder(cache_dir=cache)
    differences = {name: [] for name in METRICS}
    for source, stem, a, b, c, d, key, *stored in sample:
        request = EvaluationRequest(source_text=source, items=[
            {"question": stem, "options": {"A": a, "B": b, "C": c, "D": d}, "answer": key}])
        result = evaluate(request, embedder).items[0]
        if not result.valid:
            continue
        for name, old in zip(METRICS, stored):
            new = getattr(result.metrics, name)
            if old is not None and new is not None:
                differences[name].append(abs(new - old))

    print(f"Compared {len(differences['grade'])} thesis questions")
    for name, values in differences.items():
        if values:
            print(f"{name:22s} max |difference| = {max(values):.5f}   mean = {sum(values) / len(values):.6f}")


if __name__ == "__main__":
    main()
