"""
Fills a blind review study with SIMULATED participants, through the gateway, the way browsers would.

For demonstrations and rehearsals only. It shows ratings and answers travelling Review -> RabbitMQ -> Lab and
the study page filling up live, without needing people. The judgements are synthetic:

- every question gets a hidden random "quality" and "difficulty" that have nothing to do with its automatic
  scores, and every simulated rater and student adds personal noise;
- the agreement between the simulated raters is therefore real arithmetic on made-up data, and whatever
  correlation with the pillars appears is chance.

Never report these numbers as results. The study title and the rater names say "simulated".

    python scripts/simulate_study.py [http://localhost:8080] [--experiment ID ...] [--raters 3] [--students 7]
                                     [--questions N] [--per-cell 1] [--seed 2026]

Without --experiment the imported prototype sample is used. Without --questions every simulated student answers
all questions of the study (at most 40), so each question collects enough answers for the item analysis.
Uses only the Python standard library.
"""
import argparse
import json
import math
import os
import random
import time
import urllib.error
import urllib.request

SAMPLE_EXPERIMENT = "2026a5e0-0000-4000-8000-000000000001"
LABELS = ("A", "B", "C", "D")
DIMENSIONS = ("relevance", "clarity", "difficulty", "distractors")


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None, token=None, expect=(200,)):
        """JSON request. A 429 from the gateway's rate limit is waited out instead of failing."""
        data = json.dumps(body).encode() if body is not None else None
        for _ in range(20):
            request = urllib.request.Request(self.base + path, data=data, method=method)
            request.add_header("Accept", "application/json")
            if data is not None:
                request.add_header("Content-Type", "application/json")
            if token:
                request.add_header("Authorization", f"Bearer {token}")
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status, text = response.status, response.read().decode()
            except urllib.error.HTTPError as error:
                status, text = error.code, error.read().decode()
            if status == 429:
                print("      (the gateway limits new sessions per minute: waiting 7 s)")
                time.sleep(7)
                continue
            if status not in expect:
                raise SystemExit(f"FAILED {method} {path} -> {status}: {text[:400]}")
            return json.loads(text) if text else None
        raise SystemExit(f"FAILED {method} {path}: still rate-limited")


def clip(value: float) -> int:
    return max(1, min(5, round(value)))


class Hidden:
    """The made-up truth about one question. Seeded by its reference, so every participant meets the same one."""

    def __init__(self, seed: int, item_ref: str):
        rng = random.Random(f"{seed}|item|{item_ref}")
        self.quality = rng.gauss(0, 1)
        self.difficulty = rng.gauss(0, 1)
        self.aspect = {d: rng.gauss(0, 1) for d in DIMENSIONS}
        self.pull = [rng.choice((0.05, 0.6, 1.0, 1.4)) for _ in range(3)]  # how tempting each wrong option is


def simulated_rating(hidden: Hidden, rng: random.Random, bias: float) -> dict:
    scores = {}
    for dimension in DIMENSIONS:
        centre = hidden.difficulty if dimension == "difficulty" else 0.8 * hidden.quality + 0.6 * hidden.aspect[dimension]
        scores[dimension] = clip(3.3 + 0.9 * centre + bias + rng.gauss(0, 0.6))
    doubtful = hidden.quality < -1.5
    key_correct = rng.choices(("yes", "no", "unsure"), weights=(0.25, 0.55, 0.2) if doubtful else (0.93, 0.01, 0.06))[0]
    unusable = key_correct == "no" and rng.random() < 0.5
    return {**scores, "key_correct": key_correct, "unusable": unusable,
            "unusable_reason": "Simulated: the marked answer looks wrong." if unusable else None,
            "comment": "Simulated comment: two options say nearly the same." if scores["distractors"] == 1 else None}


def simulate_raters(api: Api, study: dict, raters: int, seed: int) -> int:
    saved = 0
    for number in range(1, raters + 1):
        name = f"Simulated rater {number}"
        rng = random.Random(f"{seed}|rater|{number}")
        bias = rng.gauss(0, 0.35)  # a strict or a lenient rater
        token = api.call("POST", "/api/review/v1/sessions", {"code": study["expert_code"], "rater_name": name})["token"]
        for entry in api.call("GET", "/api/review/v1/expert/items", token=token)["items"]:
            rating = simulated_rating(Hidden(seed, entry["item_ref"]), rng, bias)
            api.call("PUT", f"/api/review/v1/expert/ratings/{entry['item_ref']}", rating, token)
            saved += 1
        print(f"  ok  {name} rated {study['items']} questions")
    return saved


def simulate_students(api: Api, study: dict, students: int, seed: int, key_text: dict) -> int:
    answered = 0
    for number in range(1, students + 1):
        rng = random.Random(f"{seed}|student|{number}")
        ability = rng.gauss(0, 1)
        token = api.call("POST", "/api/review/v1/sessions", {"code": study["student_code"], "consent": True})["token"]
        state = api.call("GET", "/api/review/v1/quiz/current", token=token)
        while state["state"] != "completed":
            item = state["item"]
            hidden = Hidden(seed, item["item_ref"])
            # The quiz never sends the key. The simulation knows it from the Lab (the operator's side) and uses
            # it only to decide whether this made-up student "knows" the answer.
            right = next(o["label"] for o in item["options"] if o["text"] == key_text[item["item_ref"]])
            wrong = [o["label"] for o in item["options"] if o["label"] != right]
            knows = rng.random() < 1 / (1 + math.exp(-(ability - hidden.difficulty + 0.7)))
            choice = right if knows else rng.choices(wrong, weights=hidden.pull)[0]
            time.sleep(rng.uniform(0.02, 0.08))  # the Review service measures the time between showing and answering
            api.call("POST", "/api/review/v1/quiz/answers", {"item_ref": item["item_ref"], "choice": choice}, token)
            api.call("POST", "/api/review/v1/quiz/feedback", {
                "item_ref": item["item_ref"], "clarity": clip(3.5 + 0.8 * hidden.quality + rng.gauss(0, 0.7)),
                "helpfulness": clip(3.4 + 0.7 * hidden.quality + rng.gauss(0, 0.8)),
                "difficulty": clip(3.0 + 0.9 * hidden.difficulty - 0.3 * ability + rng.gauss(0, 0.6))}, token)
            answered += 1
            state = api.call("GET", "/api/review/v1/quiz/current", token=token)
        print(f"  ok  simulated student {number}: {state['correct']} of {state['total']} correct")
    return answered


def key_texts(api: Api, token: str, study_id: str, experiment_ids: list) -> dict:
    """item_ref -> text of the correct option, from the Lab, which is the only place that knows both."""
    by_item_id = {}
    for experiment_id in experiment_ids:
        offset = 0
        while True:
            page = api.call("GET", f"/api/lab/experiments/{experiment_id}/items?limit=500&offset={offset}", token=token)
            by_item_id.update({i["id"]: i["options"][i["answer"]] for i in page["items"]})
            offset += 500
            if offset >= page["total"]:
                break
    analytics = api.call("GET", f"/api/lab/studies/{study_id}/analytics", token=token)
    return {i["item_ref"]: by_item_id[i["item_id"]] for i in analytics["items"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill a blind study with simulated raters and students (demo only).")
    parser.add_argument("base", nargs="?", default="http://localhost:8080")
    parser.add_argument("--experiment", action="append", help="source experiment ID; repeatable (default: the sample)")
    parser.add_argument("--raters", type=int, default=3)
    parser.add_argument("--students", type=int, default=7)  # 3 + 7 sessions stay inside the gateway's burst limit
    parser.add_argument("--questions", type=int, default=40,
                        help="questions each simulated student answers (default: all, at most 40)")
    parser.add_argument("--per-cell", type=int, default=1, help="questions per model x strategy x domain cell")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--username", default=os.getenv("OPERATOR_USERNAME", "operator"))
    parser.add_argument("--password", default=os.getenv("OPERATOR_PASSWORD", "edugen-demo"))
    args = parser.parse_args()
    api = Api(args.base)
    experiments = args.experiment or [SAMPLE_EXPERIMENT]

    print(f"EduGen SIMULATED study against {args.base}: synthetic participants, not human data")
    token = api.call("POST", "/api/lab/auth/login", {"username": args.username, "password": args.password})["access_token"]
    study = api.call("POST", "/api/lab/studies", {
        "title": f"Simulated pilot {time.strftime('%H:%M:%S')} (synthetic participants)", "kind": "both",
        "experiment_ids": experiments, "per_cell": args.per_cell, "student_items": args.questions, "seed": args.seed},
        token, expect=(201,))
    if study["status"] != "open":
        raise SystemExit(f"FAILED: the study is {study['status']}: {study.get('publish_error')}")
    print(f"  ok  study of {study['items']} questions opened: {args.base}/lab/studies/{study['id']}")

    ratings = simulate_raters(api, study, args.raters, args.seed)
    answers = simulate_students(api, study, args.students, args.seed, key_texts(api, token, study["id"], experiments))

    deadline = time.monotonic() + 90
    while True:  # the events reach the Lab asynchronously
        analytics = api.call("GET", f"/api/lab/studies/{study['id']}/analytics", token=token)
        progress = analytics["progress"]
        if (progress["ratings"], progress["answers"], progress["feedback"]) == (ratings, answers, answers):
            break
        if time.monotonic() > deadline:
            raise SystemExit(f"FAILED: not every event reached the Lab ({progress}; expected {ratings} ratings, {answers} answers)")
        time.sleep(1)
    print(f"  ok  {ratings} ratings, {answers} answers and {answers} feedback forms arrived in the Lab")

    print("\nAgreement between the simulated raters (Krippendorff's alpha):")
    for dimension, row in analytics["agreement"].items():
        print(f"  {dimension:12s} {row['alpha']}")
    print("Correlation of the simulated judgements with the automatic metrics (Spearman; made-up data, so only chance):")
    for row in analytics["correlations"]:
        print(f"  {row['human']:30s} vs {row['metric']:12s} n={row['n']:<3d} rho={row['spearman_rho']}")
    noted = [i for i in analytics["items"] if i["student"]["dead_distractors"] or i["student"]["difficulty_note"]]
    print(f"Questions with an unused option or an extreme share of correct answers: {len(noted)}")
    print("SIMULATED DATA: for demonstrating the flow only.")


if __name__ == "__main__":
    main()
