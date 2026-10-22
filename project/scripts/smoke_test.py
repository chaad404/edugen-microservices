"""
End-to-end smoke test of a running EduGen deployment, through the gateway, like a browser would use it.
Uses only the Python standard library.

    python scripts/smoke_test.py [http://localhost:8080]
"""
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
THESIS_EXPERIMENT = "2026a5e0-0000-4000-8000-000000000001"


def call(method, path, body=None, token=None, headers=None, expect=(200,)):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, text = response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        status, text = error.code, error.read().decode()
    if status not in expect:
        raise SystemExit(f"FAILED {method} {path} -> {status}: {text[:400]}")
    try:
        return json.loads(text) if text else None
    except json.JSONDecodeError:
        return text  # plain-text answers such as the gateway's /healthz


def step(message):
    print(f"  ok  {message}")


def follow_stream(token, channel, until, timeout=240):
    """Reads the Server-Sent Events stream through the gateway until an event of type `until`."""
    ticket = call("POST", "/api/lab/auth/stream-tickets", {"channel": channel}, token)["ticket"]
    url = f"{BASE}/api/lab/events/stream?channel={channel}&ticket={ticket}"
    seen, event = [], None
    deadline = time.monotonic() + timeout
    with urllib.request.urlopen(urllib.request.Request(url), timeout=40) as stream:
        assert stream.headers["Content-Type"].startswith("text/event-stream")
        while time.monotonic() < deadline:
            line = stream.readline().decode().rstrip("\n")
            if line.startswith("event: "):
                event = line[7:]
                seen.append(event)
                if event == until:
                    return seen
    raise SystemExit(f"FAILED: no {until} event within {timeout} s (saw {seen[-5:]})")


def main():
    print(f"EduGen smoke test against {BASE}")
    call("GET", "/healthz")
    token = call("POST", "/api/lab/auth/login", {"username": "operator", "password": "edugen-demo"})["access_token"]
    step("operator login")

    models = {m["alias"]: m for m in call("GET", "/api/lab/models", token=token)}
    assert models["simulator"]["available"]
    step(f"model catalog from the Generator: {', '.join(models)}")
    framework = call("GET", "/api/lab/framework", token=token)
    step(f"framework {framework['version']} from the Evaluator")
    call("GET", "/api/review/internal/v1/studies", expect=(404,))
    step("internal Review endpoints are hidden by the gateway")

    body = {"name": f"Smoke test {time.strftime('%H:%M:%S')}", "topic_ids": ["NETCOMP-DEMO-1"],
            "models": ["simulator"], "strategies": ["baseline", "prompt_v2", "verify_repair"], "questions_per_job": 3}
    key = str(uuid.uuid4())
    experiment = call("POST", "/api/lab/experiments", body, token, {"Idempotency-Key": key}, expect=(202,))
    again = call("POST", "/api/lab/experiments", body, token, {"Idempotency-Key": key}, expect=(202,))
    assert again["id"] == experiment["id"]
    step(f"experiment accepted (202), the same idempotency key returns the same experiment {experiment['id'][:8]}")

    events = follow_stream(token, f"experiment:{experiment['id']}", "experiment.completed")
    step(f"followed the run over SSE: {len(events)} events, last {events[-1]}")
    detail = call("GET", f"/api/lab/experiments/{experiment['id']}", token=token)
    assert detail["status"] == "completed", [j["error"] for j in detail["jobs"]]
    summary = call("GET", f"/api/lab/experiments/{experiment['id']}/summary", token=token)
    bands = {g["strategy"]: g["pillars"]["P1"]["band_of_mean"] for g in summary["groups"]}
    assert all(bands.values())
    step(f"three jobs scored by the Evaluator, P1 bands {bands}")

    study = call("POST", "/api/lab/studies", {"title": "Smoke study", "kind": "both", "per_cell": 1, "student_items": 3,
                                              "experiment_ids": [THESIS_EXPERIMENT]}, token, expect=(201,))
    assert study["status"] == "open", study
    step(f"blind study of {study['items']} thesis questions opened: {study['expert_code']}, {study['student_code']}")

    expert = call("POST", "/api/review/v1/sessions", {"code": study["expert_code"], "rater_name": "Smoke rater"})["token"]
    for _ in range(3):
        item = call("GET", "/api/review/v1/expert/next", token=expert)["item"]
        assert set(item) == {"item_ref", "topic_label", "domain", "question", "options", "answer"}
        call("PUT", f"/api/review/v1/expert/ratings/{item['item_ref']}", {"relevance": 4, "clarity": 4, "difficulty": 3,
                                                                          "distractors": 3, "key_correct": "yes"}, expert)
    step("expert rated 3 questions without seeing any model")

    student = call("POST", "/api/review/v1/sessions", {"code": study["student_code"], "consent": True})["token"]
    for _ in range(3):
        question = call("GET", "/api/review/v1/quiz/current", token=student)
        ref = question["item"]["item_ref"]
        call("POST", "/api/review/v1/quiz/answers", {"item_ref": ref, "choice": "A"}, student)
        state = call("POST", "/api/review/v1/quiz/feedback", {"item_ref": ref, "clarity": 4, "helpfulness": 4, "difficulty": 2}, student)
    assert state["state"] == "completed"
    step(f"student finished the quiz: {state['correct']} of 3 correct, code {state['completion_code']}")

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        progress = call("GET", f"/api/lab/studies/{study['id']}/analytics", token=token)["progress"]
        if progress["ratings"] == 3 and progress["answers"] == 3 and progress["feedback"] == 3:
            break
        time.sleep(1)
    else:
        raise SystemExit(f"FAILED: review events did not reach the Lab ({progress})")
    step("ratings, answers and feedback travelled Review -> RabbitMQ -> Lab")
    print("PASSED")


if __name__ == "__main__":
    main()
