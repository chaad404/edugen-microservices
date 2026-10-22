import json

import pytest
from sqlalchemy import func, select

from conftest import SEED
from lab.messages import REVIEW_ANSWER, REVIEW_FEEDBACK, REVIEW_RATING, envelope
from lab.models import Item, Job, StudyItem
from lab.seed import THESIS_EXPERIMENT_ID, import_thesis_sample
from lab.studies import handle_review_event


@pytest.fixture
def thesis(session_factory):
    with session_factory() as session:
        assert import_thesis_sample(session, SEED / "thesis_sample.json") is True
        session.commit()
    return THESIS_EXPERIMENT_ID


def make_study(client, auth, thesis, per_cell=1, **extra):
    body = {"title": "Pilot review", "kind": "both", "experiment_ids": [thesis], "per_cell": per_cell, **extra}
    return client.post("/studies", json=body, headers=auth)


def test_the_thesis_sample_is_imported_once_with_its_recorded_scores(session_factory, thesis, client, auth):
    with session_factory() as session:
        assert import_thesis_sample(session, SEED / "thesis_sample.json") is False
        assert session.scalar(select(func.count()).select_from(Job)) == 36
        items = list(session.scalars(select(Item)))
    assert len(items) == 108 and all(i.metrics_source == "thesis" and i.alignment is not None for i in items)
    summary = client.get(f"/experiments/{thesis}/summary", headers=auth).json()
    assert {g["model"] for g in summary["groups"]} == {"cohere", "gpt-oss", "llama33", "mistral-small"}
    assert {g["strategy"] for g in summary["groups"]} == {"baseline", "rag", "multi_agent"}


def test_a_study_is_a_stratified_sample_sent_blinded_to_the_review_service(client, auth, thesis, fakes):
    response = make_study(client, auth, thesis)
    assert response.status_code == 201
    study = response.json()
    assert study["status"] == "open" and study["expert_code"] == "EXP-ABCD"
    assert study["items"] == 36  # 4 models x 3 conditions x 3 domains, one question per cell

    call = fakes.review.calls[0]
    assert call["key"] == study["id"] and call["token"]
    payload = call["payload"]
    # Blindness by data ownership: nothing that identifies the model or condition leaves the Lab
    for item in payload["items"]:
        assert set(item) == {"item_ref", "topic_label", "domain", "question", "options", "answer"}
    text = json.dumps(payload)
    for leak in ("gpt-oss", "llama33", "mistral", "cohere", "multi_agent", "openrouter", "alignment"):
        assert leak not in text


def test_the_same_seed_gives_the_same_sample(client, auth, thesis, session_factory):
    first, second = make_study(client, auth, thesis).json(), make_study(client, auth, thesis).json()
    with session_factory() as session:
        items = [sorted(si.item_id for si in session.scalars(select(StudyItem).where(StudyItem.study_id == s["id"])))
                 for s in (first, second)]
    assert items[0] == items[1]


def test_publishing_is_retried_when_the_review_service_was_down(client, auth, thesis, fakes):
    fakes.review.down = True
    study = make_study(client, auth, thesis).json()
    assert study["status"] == "draft" and "Review unreachable" in study["publish_error"]
    assert client.post(f"/studies/{study['id']}/publish", headers=auth).status_code == 503
    fakes.review.down = False
    retried = client.post(f"/studies/{study['id']}/publish", headers=auth).json()
    assert retried["status"] == "open" and retried["student_code"] == "STU-WXYZ"


def _rating(study_id, item_ref, rater, revision=1, relevance=4, **extra):
    return envelope(REVIEW_RATING, {"study_id": study_id, "item_ref": item_ref, "rater": rater, "relevance": relevance,
                                    "clarity": 4, "difficulty": 3, "distractors": 3, "key_correct": "yes",
                                    "unusable": False, "comment": None, "revision": revision, **extra})


def test_review_events_are_stored_idempotently_and_late_revisions_lose(client, auth, thesis, session_factory):
    study = make_study(client, auth, thesis).json()
    with session_factory() as session:
        ref = session.scalars(select(StudyItem.item_ref).where(StudyItem.study_id == study["id"])).first()
        newer = _rating(study["id"], ref, "rater-1", revision=2, relevance=5)
        assert handle_review_event(session, newer) == "stored"
        assert handle_review_event(session, newer) == "duplicate"
        assert handle_review_event(session, _rating(study["id"], ref, "rater-1", revision=1, relevance=1)) == "stored"
        assert handle_review_event(session, _rating(study["id"], "unknown-ref", "rater-1")) == "unknown_item"
        assert handle_review_event(session, _rating(study["id"], ref, "rater-1", relevance=9)) == "invalid"
        session.commit()
    analytics = client.get(f"/studies/{study['id']}/analytics", headers=auth).json()
    rated = next(i for i in analytics["items"] if i["item_ref"] == ref)
    assert rated["expert"]["relevance"] == 5 and rated["expert"]["ratings"] == 1


def test_analytics_combine_human_and_automatic_evaluation(client, auth, thesis, session_factory):
    study = make_study(client, auth, thesis).json()
    with session_factory() as session:
        refs = list(session.scalars(select(StudyItem).where(StudyItem.study_id == study["id"]).order_by(StudyItem.position)))
        for n, si in enumerate(refs[:8]):
            for rater, shift in (("rater-1", 0), ("rater-2", 1)):
                handle_review_event(session, _rating(study["id"], si.item_ref, rater, relevance=1 + (n + shift) % 5))
            for p, chosen in enumerate(["A", "B", si.item.answer]):
                handle_review_event(session, envelope(REVIEW_ANSWER, {
                    "study_id": study["id"], "item_ref": si.item_ref, "participant": f"student-{p}",
                    "chosen": chosen, "correct": chosen == si.item.answer, "time_ms": 9000}))
                handle_review_event(session, envelope(REVIEW_FEEDBACK, {
                    "study_id": study["id"], "item_ref": si.item_ref, "participant": f"student-{p}",
                    "clarity": 4, "helpfulness": 3, "difficulty": 2}))
        session.commit()

    analytics = client.get(f"/studies/{study['id']}/analytics", headers=auth).json()
    assert analytics["progress"] == {"raters": 2, "ratings": 16, "participants": 3, "answers": 24, "feedback": 24}
    assert analytics["agreement"]["relevance"]["items_with_2_raters"] == 8
    assert analytics["agreement"]["relevance"]["alpha"] is not None
    assert analytics["agreement"]["key_correct"]["alpha"] is None  # everyone said "yes": no variation
    relevance = next(c for c in analytics["correlations"] if c["human"] == "expert_relevance")
    assert relevance["n"] == 8 and relevance["spearman_rho"] is not None
    first = analytics["items"][0]
    assert first["student"]["attempts"] == 3 and first["model"] in {"cohere", "gpt-oss", "llama33", "mistral-small"}
    assert first["student"]["p_value"] is not None and sum(first["student"]["option_counts"].values()) == 3
