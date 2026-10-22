from conftest import join, outbox

FEEDBACK = {"clarity": 4, "helpfulness": 3, "difficulty": 2}


def key_position(question: dict) -> str:
    """The shown label of the correct option (the key's text starts with 'key text')."""
    return next(o["label"] for o in question["item"]["options"] if o["text"].startswith("key text"))


def test_students_must_accept_the_notice(client, study):
    response = client.post("/v1/sessions", json={"code": study["student_code"]})
    assert response.status_code == 422 and response.json()["type"] == "urn:edugen:problem:consent-required"


def test_options_are_shuffled_per_student_but_the_content_is_the_same(client, study):
    orders = set()
    for _ in range(6):
        student = join(client, study["student_code"], consent=True)
        question = client.get("/v1/quiz/current", headers=student).json()
        assert question["state"] == "question" and question["total"] == 4
        assert [o["label"] for o in question["item"]["options"]] == ["A", "B", "C", "D"]
        orders.add(key_position(question))
    assert len(orders) > 1  # the key is not always at A, unlike the model's raw output


def test_the_linear_flow_answer_then_feedback_then_next(client, study, session_factory):
    student = join(client, study["student_code"], consent=True)
    question = client.get("/v1/quiz/current", headers=student).json()
    ref = question["item"]["item_ref"]
    assert client.post("/v1/quiz/feedback", json={"item_ref": ref, **FEEDBACK}, headers=student).status_code == 409

    other_ref = next(i["item_ref"] for i in study["body"]["items"] if i["item_ref"] != ref)
    skip = client.post("/v1/quiz/answers", json={"item_ref": other_ref, "choice": "A"}, headers=student)
    assert skip.status_code == 409 and skip.json()["type"] == "urn:edugen:problem:not-current-question"

    choice = key_position(question)
    assert client.post("/v1/quiz/answers", json={"item_ref": ref, "choice": choice}, headers=student).json() == {"state": "feedback"}
    assert client.post("/v1/quiz/answers", json={"item_ref": ref, "choice": choice}, headers=student).status_code == 200
    changed = client.post("/v1/quiz/answers", json={"item_ref": ref, "choice": "D" if choice != "D" else "C"}, headers=student)
    assert changed.status_code == 409 and changed.json()["type"] == "urn:edugen:problem:answer-locked"

    assert client.get("/v1/quiz/current", headers=student).json()["state"] == "feedback"  # resume shows the same step
    assert client.post("/v1/quiz/feedback", json={"item_ref": ref, **FEEDBACK}, headers=student).json() == {"state": "question"}
    assert client.get("/v1/quiz/current", headers=student).json()["position"] == 2

    events = outbox(session_factory)
    assert [e["type"] for e in events] == ["review.answer.submitted", "review.feedback.submitted"]
    answer = events[0]["payload"]
    assert answer["chosen"] == "A" and answer["correct"] is True and answer["time_ms"] >= 0  # stored in original labels
    assert "rater" not in answer and len(answer["participant"]) == 36  # anonymous student ID only


def test_a_wrong_answer_maps_back_to_the_original_label(client, study, session_factory):
    student = join(client, study["student_code"], consent=True)
    question = client.get("/v1/quiz/current", headers=student).json()
    wrong = next(o for o in question["item"]["options"] if not o["text"].startswith("key text"))
    client.post("/v1/quiz/answers", json={"item_ref": question["item"]["item_ref"], "choice": wrong["label"]}, headers=student)
    payload = outbox(session_factory)[0]["payload"]
    assert payload["correct"] is False
    assert payload["chosen"] == wrong["text"].split()[1].upper()  # "wrong b 3" was option B in the original


def test_finishing_the_quiz_gives_a_score_and_a_completion_code(client, study):
    student = join(client, study["student_code"], consent=True)
    result = None
    for n in range(4):
        question = client.get("/v1/quiz/current", headers=student).json()
        choice = key_position(question) if n % 2 == 0 else next(
            o["label"] for o in question["item"]["options"] if not o["text"].startswith("key text"))
        client.post("/v1/quiz/answers", json={"item_ref": question["item"]["item_ref"], "choice": choice}, headers=student)
        result = client.post("/v1/quiz/feedback", json={"item_ref": question["item"]["item_ref"], **FEEDBACK},
                             headers=student).json()
    assert result["state"] == "completed" and result["correct"] == 2 and len(result["completion_code"]) == 8
    assert client.get("/v1/quiz/current", headers=student).json()["state"] == "completed"
    assert client.get("/v1/sessions/me", headers=student).json()["completed"] is True
