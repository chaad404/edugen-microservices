import json

from sqlalchemy import func, select

from lab.models import Experiment, Item, Job, Topic
from lab.seed import RECORDED_FORMAT, import_recorded_runs

RUN_ID = "11111111-2222-4333-8444-555555555555"
METRICS = {"alignment": 0.71, "alignment_lexical": 0.31, "grade": 11.2, "plausibility": 0.52,
           "plausibility_lexical": 0.2, "diversity": 0.58}


def question(position: int, answer: str) -> dict:
    return {"position": position, "question": f"Which statement about slow start number {position} is correct?",
            "options": {"A": "alpha one", "B": "beta two", "C": "gamma three", "D": "delta four"}, "answer": answer,
            "evidence": "slow start doubles the window", "valid": True, "metrics": METRICS,
            "flags": ["length_cue"] if position == 0 else [], "quality": 8}


def recorded_run(**experiment) -> dict:
    """A run as scripts/export_run.py writes it: one finished job with two questions and one failed job."""
    return {
        "format": RECORDED_FORMAT,
        "experiment": {"id": RUN_ID, "name": "Recorded live run", "description": "Two jobs", "created_by": "operator",
                       "status": "completed_with_failures", "questions_per_job": 2, "models": ["llama33"],
                       "strategies": ["baseline", "prompt_v2"], "created_at": "2026-10-23T13:49:35+00:00",
                       "finished_at": "2026-10-23T14:21:50+00:00", **experiment},
        "topics": [{"topic_id": "NETCOMP-DEMO-1", "domain": "NETCOMP", "title": "TCP congestion control"},
                   {"topic_id": "OTHER-ELSEWHERE-1", "domain": "OTHER", "title": "A topic this deployment lacks"}],
        "jobs": [
            {"id": "job-ok", "topic_id": "NETCOMP-DEMO-1", "model": "llama33", "strategy": "prompt_v2",
             "status": "succeeded", "provider": "openrouter", "requested_model_id": "meta-llama/llama-3.3-70b-instruct",
             "returned_model_id": "meta-llama/llama-3.3-70b-instruct", "simulated": False, "attempts": 1, "calls": 1,
             "prompt_tokens": 1053, "completion_tokens": 477, "cost_usd": 0.001086, "latency_seconds": 5.3,
             "strategy_status": "valid", "error_kind": None, "error": None,
             "trace": {"key_balance": "shuffled", "raw_answers": ["A", "A"], "settings": {"temperature": 0.7}},
             "created_at": "2026-10-23T13:49:35+00:00", "finished_at": "2026-10-23T13:50:02+00:00",
             "items": [question(0, "C"), question(1, "D")]},
            {"id": "job-failed", "topic_id": "OTHER-ELSEWHERE-1", "model": "llama33", "strategy": "baseline",
             "status": "failed", "provider": "openrouter", "requested_model_id": "meta-llama/llama-3.3-70b-instruct",
             "simulated": False, "attempts": 4, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0,
             "error_kind": "provider_error", "error": "HTTP 429", "trace": {"settings": {"temperature": 0.7}},
             "created_at": "2026-10-23T13:49:36+00:00", "finished_at": "2026-10-23T13:52:00+00:00", "items": []},
        ],
    }


def write(folder, name: str, data: dict):
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(data), encoding="utf-8")


def test_a_recorded_run_is_imported_once_with_its_jobs_questions_and_traces(session_factory, client, auth, tmp_path):
    folder = tmp_path / "recorded"
    write(folder, "run.json", recorded_run())
    write(folder, "other.json", {"format": "something-else", "experiment": {"id": "x"}})  # skipped, not an error
    with session_factory() as session:
        assert import_recorded_runs(session, folder) == 1
        session.commit()
        assert import_recorded_runs(session, folder) == 0  # every start of the service may run the import
        session.commit()
        assert session.scalar(select(func.count()).select_from(Job).where(Job.experiment_id == RUN_ID)) == 2
        assert session.scalar(select(func.count()).select_from(Item)) == 2
        unknown = session.scalar(select(Topic).where(Topic.topic_id == "OTHER-ELSEWHERE-1"))
        assert unknown.origin == "recorded" and unknown.source_text is None  # results only, nothing to generate from
    assert import_recorded_runs(None, tmp_path / "no-such-folder") == 0

    detail = client.get(f"/experiments/{RUN_ID}", headers=auth).json()
    assert detail["origin"] == "recorded" and detail["status"] == "completed_with_failures"  # never shown as run here
    assert detail["created_at"].startswith("2026-10-23T13:49:35") and detail["cost_usd"] == 0.001086
    jobs = {j["id"]: j for j in detail["jobs"]}
    assert jobs["job-ok"]["trace"]["raw_answers"] == ["A", "A"] and jobs["job-ok"]["settings"] == {"temperature": 0.7}
    assert jobs["job-failed"]["error_kind"] == "provider_error" and jobs["job-failed"]["items"] == 0

    group = next(g for g in client.get(f"/experiments/{RUN_ID}/summary", headers=auth).json()["groups"]
                 if g["strategy"] == "prompt_v2")
    assert group["pillars"]["P1"]["mean"] == 0.71 and group["flags"] == {"length_cue": 1}
    # The stored keys are the balanced ones; the letters the model wrote come from the recorded trace
    assert group["key_positions"] == {"A": 0, "B": 0, "C": 1, "D": 1} and group["raw_key_positions"]["A"] == 2


def test_a_recorded_title_is_refreshed_but_a_run_made_here_keeps_its_own_record(session_factory, tmp_path):
    folder = tmp_path / "recorded"
    write(folder, "run.json", recorded_run())
    with session_factory() as session:
        import_recorded_runs(session, folder)
        session.commit()
    write(folder, "run.json", recorded_run(name="Reworded"))
    with session_factory() as session:
        assert import_recorded_runs(session, folder) == 0
        session.commit()
        assert session.get(Experiment, RUN_ID).name == "Reworded"
        session.get(Experiment, RUN_ID).origin = "live"  # as if this deployment had made the run itself
        session.commit()
    write(folder, "run.json", recorded_run(name="Reworded again"))
    with session_factory() as session:
        assert import_recorded_runs(session, folder) == 0
        session.commit()
        assert session.get(Experiment, RUN_ID).name == "Reworded"
