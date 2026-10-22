"""
Exports thesis results for the Lab: a small public sample (committed), or the full October 2026 comparison
for local use only (write it under project/data/local/, which git ignores).

The thesis database is opened read-only. Topic source texts, prompts, raw model outputs and generation traces
are never exported: they contain the topic texts, which were drafted from other students' notes.

    python export_thesis_sample.py <thesis app.db> <output.json> [--topics-per-domain 1] [--per-cell 3]
    python export_thesis_sample.py <thesis app.db> project/data/local/thesis_full.json --full
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

# The October 2026 comparison: three conditions on the same models, hosts and days
OCTOBER = {"BATCH-20261019-221228-cba643d5": "baseline",
           "BATCH-20261019-222437-7dbb69b1": "rag",
           "BATCH-20261019-223556-62722f5c": "multi_agent"}
MODELS = ("cohere", "gpt-oss", "llama33", "mistral-small")

QUERY = f"""
SELECT r.run_id, r.model_name, r.q_index, r.latency_seconds, r.prompt_tokens, r.completion_tokens, r.cost_usd,
       r.status, r.provider, r.requested_model_id, r.returned_model_id,
       t.topic_id, t.domain, t.title,
       q.id, q.question_stem, q.option_a, q.option_b, q.option_c, q.option_d, q.correct_option,
       e.score_dense_semantic_alignment, e.score_semantic_alignment, e.score_linguistic_complexity,
       e.score_dense_distractor_plausibility, e.score_distractor_plausibility, e.score_distractor_diversity
FROM generation_runs r
JOIN topics t ON t.id = r.topic_fk
JOIN generated_questions q ON q.run_fk = r.id
JOIN evaluation_results e ON e.question_fk = q.id
WHERE r.run_id IN ({",".join("?" * len(OCTOBER))}) AND r.is_simulated = 0
ORDER BY t.topic_id, r.model_name, r.run_id, r.q_index
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("database")
    parser.add_argument("output")
    parser.add_argument("--topics-per-domain", type=int, default=1)
    parser.add_argument("--per-cell", type=int, default=3, help="questions kept per topic x model x condition")
    parser.add_argument("--full", action="store_true", help="every October question (local use only)")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.database}?mode=ro&immutable=1", uri=True)
    cells = defaultdict(list)
    topics = {}
    for row in conn.execute(QUERY, tuple(OCTOBER)):
        run_id, model, *_rest = row
        topic_id, domain, title = row[11], row[12], row[13]
        topics[topic_id] = {"topic_id": topic_id, "domain": domain, "title": title}
        cells[(topic_id, model, OCTOBER[run_id])].append(row)

    complete = sorted(t for t in topics if all((t, m, c) in cells for m in MODELS for c in OCTOBER.values()))
    if args.full:
        chosen = sorted(topics)
    else:
        chosen = []
        for domain in sorted({topics[t]["domain"] for t in complete}):
            chosen += [t for t in complete if topics[t]["domain"] == domain][:args.topics_per_domain]

    batches = []
    for (topic_id, model, condition), rows in sorted(cells.items()):
        if topic_id not in chosen:
            continue
        kept = rows if args.full else rows[:args.per_cell]
        first = rows[0]  # every question row of one call repeats the call's latency, tokens and cost
        batches.append({
            "batch_id": first[0], "topic_id": topic_id, "model": model, "condition": condition,
            "provider": first[8], "requested_model_id": first[9], "returned_model_id": first[10],
            "latency_seconds": first[3], "prompt_tokens": first[4], "completion_tokens": first[5],
            "cost_usd": first[6], "status": first[7], "calls": 1,
            "items": [{
                "thesis_question_id": r[14], "question": r[15],
                "options": {"A": r[16], "B": r[17], "C": r[18], "D": r[19]}, "answer": r[20],
                "metrics": {"alignment": r[21], "alignment_lexical": r[22], "grade": r[23],
                            "plausibility": r[24], "plausibility_lexical": r[25], "diversity": r[26]},
            } for r in kept],
        })

    n_items = sum(len(b["items"]) for b in batches)
    output = {
        "name": "Thesis results: October 2026 comparison" + ("" if args.full else " (public sample)"),
        "description": (f"{len(chosen)} topics x {len(MODELS)} models x {len(OCTOBER)} conditions (baseline, RAG, "
                        f"multi-agent), {n_items} questions with the scores recorded by the thesis framework. "
                        "Topic source texts are not included."),
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "questions_per_job": 5, "topics": [topics[t] for t in chosen], "batches": batches,
    }
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=1)
    print(f"Wrote {len(batches)} batches, {n_items} questions, topics: {', '.join(chosen)}")


if __name__ == "__main__":
    main()
