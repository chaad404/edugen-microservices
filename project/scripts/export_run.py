"""
Exports one experiment of a running Lab as a file that another deployment imports at start-up: the jobs with
their traces, the generated questions and the scores they got. Put the file into services/lab/seed/recorded/
and every fresh deployment shows the run, marked as recorded, without API keys or cost.

Only what the Lab's operator API returns is exported: no topic source text, no prompt, no raw model reply.
Publish a run only if its topics may be published (the demo topics may).

    python scripts/export_run.py <experiment id> <output.json> [http://localhost:8080]
                                 [--name "Title to show"] [--description "What a reader should know"]

Uses only the Python standard library. The operator's sign-in comes from OPERATOR_USERNAME / OPERATOR_PASSWORD.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

FORMAT = "edugen-recorded-run/1"  # the Lab's import (lab/seed.py) accepts exactly this
EXPERIMENT_FIELDS = ("id", "name", "description", "status", "questions_per_job", "models", "strategies", "created_by",
                     "created_at", "finished_at")
JOB_FIELDS = ("id", "topic_id", "model", "strategy", "status", "provider", "requested_model_id", "returned_model_id",
              "simulated", "attempts", "calls", "prompt_tokens", "completion_tokens", "cost_usd", "latency_seconds",
              "strategy_status", "error_kind", "error", "trace", "created_at", "dispatched_at", "generated_at",
              "finished_at")
ITEM_FIELDS = ("position", "question", "options", "answer", "evidence", "valid", "metrics", "flags", "quality")
# A provider's error text is stored with a failed job. It must never carry a credential into a public file.
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|api[_-]?key\"?\s*[:=]\s*\"?[A-Za-z0-9_-]{16,})", re.I)


def build_export(experiment: dict, items: list, topics: list) -> dict:
    """
    The recorded-run file from three answers of the Lab API: GET /experiments/{id} (with its jobs),
    all pages of GET /experiments/{id}/items, and GET /topics.
    """
    if experiment["status"] == "running":
        raise ValueError("The experiment is still running: export it when it has finished.")
    by_job = {}
    for item in items:
        by_job.setdefault(item["job_id"], []).append({name: item.get(name) for name in ITEM_FIELDS})
    titles = {t["topic_id"]: t for t in topics}
    used = sorted({job["topic_id"] for job in experiment["jobs"]})
    export = {
        "format": FORMAT,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": {name: experiment.get(name) for name in EXPERIMENT_FIELDS},
        "topics": [{"topic_id": t, "domain": titles[t]["domain"], "title": titles[t]["title"]} for t in used],
        "jobs": [{**{name: job.get(name) for name in JOB_FIELDS},
                  "items": sorted(by_job.get(job["id"], []), key=lambda i: i["position"])}
                 for job in experiment["jobs"]],
    }
    leak = SECRET.search(json.dumps(export))
    if leak:
        raise ValueError(f"The export contains something that looks like a credential ({leak.group(0)[:12]}...): not written.")
    return export


def call(base: str, method: str, path: str, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"FAILED {method} {path} -> {error.code}: {error.read().decode()[:300]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one experiment of a running Lab as a recorded-run file.")
    parser.add_argument("experiment_id")
    parser.add_argument("output")
    parser.add_argument("base", nargs="?", default="http://localhost:8080")
    parser.add_argument("--name", help="title of the recorded run (default: the experiment's name)")
    parser.add_argument("--description", help="description of the recorded run (default: the experiment's)")
    args = parser.parse_args()
    experiment_id, output, base = args.experiment_id, args.output, args.base.rstrip("/")
    token = call(base, "POST", "/api/lab/auth/login", {
        "username": os.getenv("OPERATOR_USERNAME", "operator"),
        "password": os.getenv("OPERATOR_PASSWORD", "edugen-demo")})["access_token"]
    experiment = call(base, "GET", f"/api/lab/experiments/{experiment_id}", token=token)
    if args.name:
        experiment["name"] = args.name
    if args.description:
        experiment["description"] = args.description
    items, offset = [], 0
    while True:
        page = call(base, "GET", f"/api/lab/experiments/{experiment_id}/items?limit=500&offset={offset}", token=token)
        items += page["items"]
        offset += 500
        if offset >= page["total"]:
            break
    try:
        export = build_export(experiment, items, call(base, "GET", "/api/lab/topics", token=token))
    except ValueError as error:
        raise SystemExit(f"FAILED: {error}")
    with open(output, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(export, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"Wrote {output}: {experiment['name']!r}, {len(export['jobs'])} jobs, {len(items)} questions")


if __name__ == "__main__":
    main()
