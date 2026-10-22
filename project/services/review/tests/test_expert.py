from conftest import RATING, join, outbox, study_body


def test_experts_need_a_pseudonym(client, study):
    response = client.post("/v1/sessions", json={"code": study["expert_code"]})
    assert response.status_code == 422 and response.json()["type"] == "urn:edugen:problem:rater-name-required"


def test_each_rater_gets_a_stable_order_of_all_items(client, study):
    first = client.get("/v1/expert/items", headers=join(client, study["expert_code"], rater_name="Rater 1")).json()
    again = client.get("/v1/expert/items", headers=join(client, study["expert_code"], rater_name="Rater 1")).json()
    other = client.get("/v1/expert/items", headers=join(client, study["expert_code"], rater_name="Rater 2")).json()
    refs = lambda listing: [i["item_ref"] for i in listing["items"]]  # noqa: E731
    assert refs(first) == refs(again)
    assert sorted(refs(first)) == sorted(refs(other)) and len(refs(first)) == 6


def test_rating_requires_all_four_scales_in_range(client, study):
    expert = join(client, study["expert_code"], rater_name="Rater 1")
    ref = client.get("/v1/expert/next", headers=expert).json()["item"]["item_ref"]
    missing = {k: v for k, v in RATING.items() if k != "distractors"}
    assert client.put(f"/v1/expert/ratings/{ref}", json=missing, headers=expert).status_code == 422
    assert client.put(f"/v1/expert/ratings/{ref}", json={**RATING, "clarity": 6}, headers=expert).status_code == 422


def test_a_rating_is_stored_announced_and_can_be_revised(client, study, session_factory):
    expert = join(client, study["expert_code"], rater_name="Rater 1")
    item = client.get("/v1/expert/next", headers=expert).json()["item"]
    assert item["answer"] == "A"  # experts judge whether the marked key is correct
    saved = client.put(f"/v1/expert/ratings/{item['item_ref']}", json=RATING, headers=expert).json()
    assert saved == {"saved": True, "revision": 1, "rated": 1, "total": 6}
    revised = client.put(f"/v1/expert/ratings/{item['item_ref']}", json={**RATING, "relevance": 2}, headers=expert).json()
    assert revised["revision"] == 2 and revised["rated"] == 1

    events = outbox(session_factory)
    assert [e["type"] for e in events] == ["review.rating.submitted"] * 2
    payload = events[1]["payload"]
    assert payload["rater"] == "Rater 1" and payload["relevance"] == 2 and payload["revision"] == 2
    assert payload["study_id"] == study["study_id"]
    assert client.get(f"/v1/expert/items/{item['item_ref']}", headers=expert).json()["rating"]["relevance"] == 2


def test_resuming_keeps_the_progress_and_finishing_completes_the_session(client, study):
    expert = join(client, study["expert_code"], rater_name="Rater 1")
    for _ in range(6):
        ref = client.get("/v1/expert/next", headers=expert).json()["item"]["item_ref"]
        client.put(f"/v1/expert/ratings/{ref}", json=RATING, headers=expert)
    resumed = join(client, study["expert_code"], rater_name="Rater 1")
    assert client.get("/v1/expert/next", headers=resumed).json() == {"done": True, "total": 6, "rated": 6}
    me = client.get("/v1/sessions/me", headers=resumed).json()
    assert me["completed"] is True and me["role"] == "expert" and me["instructions"]


def test_record_level_authorization(client, operator, study):
    other = study_body()
    client.post("/internal/v1/studies", json=other, headers={**operator, "Idempotency-Key": other["study_id"]})
    expert = join(client, study["expert_code"], rater_name="Rater 1")
    foreign_ref = other["items"][0]["item_ref"]
    assert client.get(f"/v1/expert/items/{foreign_ref}", headers=expert).status_code == 404
    assert client.put(f"/v1/expert/ratings/{foreign_ref}", json=RATING, headers=expert).status_code == 404
    student = join(client, study["student_code"], consent=True)
    assert client.get("/v1/expert/next", headers=student).status_code == 403
    assert client.get("/v1/quiz/current", headers=expert).status_code == 403
    assert client.get("/v1/expert/next").status_code == 401
