from conftest import join, operator_token, study_body


def post_study(client, operator, body, key="same"):
    return client.post("/internal/v1/studies", json=body,
                       headers={**operator, "Idempotency-Key": body["study_id"] if key == "same" else key})


def test_a_study_gets_one_code_per_role_and_retrying_is_safe(client, operator):
    body = study_body()
    first = post_study(client, operator, body)
    again = post_study(client, operator, body)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json() == again.json()
    assert first.json()["expert_code"].startswith("EXP-") and first.json()["student_code"].startswith("STU-")


def test_the_same_study_id_with_different_content_is_a_conflict(client, operator):
    body = study_body()
    post_study(client, operator, body)
    changed = {**body, "title": "Another study"}
    response = post_study(client, operator, changed)
    assert response.status_code == 409 and response.json()["type"] == "urn:edugen:problem:study-conflict"


def test_the_idempotency_key_must_be_the_study_id(client, operator):
    assert post_study(client, operator, study_body(), key="something-else").status_code == 400


def test_only_the_lab_operator_can_create_studies(client):
    body = study_body()
    assert client.post("/internal/v1/studies", json=body, headers={"Idempotency-Key": body["study_id"]}).status_code == 401
    student_like = {"Authorization": f"Bearer {operator_token(role='student')}", "Idempotency-Key": body["study_id"]}
    assert client.post("/internal/v1/studies", json=body, headers=student_like).status_code == 403


def test_blindness_by_contract_extra_fields_are_rejected(client, operator):
    body = study_body()
    body["items"][0]["model"] = "llama33"  # must never be accepted, even by mistake
    response = post_study(client, operator, body)
    assert response.status_code == 422
    assert any("model" in str(error["loc"]) for error in response.json()["errors"])
    leaky = {**study_body(), "strategy": "baseline"}
    assert post_study(client, operator, leaky).status_code == 422


def test_invalid_studies_are_rejected(client, operator):
    duplicated = study_body()
    duplicated["items"][1]["item_ref"] = duplicated["items"][0]["item_ref"]
    assert post_study(client, operator, duplicated).status_code == 422
    three_options = study_body()
    del three_options["items"][0]["options"]["D"]
    assert post_study(client, operator, three_options).status_code == 422


def test_a_study_for_experts_only_has_no_student_code(client, operator):
    codes = post_study(client, operator, study_body(kind="expert")).json()
    assert codes["student_code"] is None and codes["expert_code"]


def test_unknown_codes_are_not_found(client):
    response = client.post("/v1/sessions", json={"code": "EXP-NOPE99", "rater_name": "Rater 1"})
    assert response.status_code == 404


def test_progress_is_for_the_operator(client, operator, study):
    join(client, study["expert_code"], rater_name="Rater 1")
    join(client, study["student_code"], consent=True)
    assert client.get(f"/v1/studies/{study['study_id']}/progress").status_code == 401
    progress = client.get(f"/v1/studies/{study['study_id']}/progress", headers=operator).json()
    assert progress["items"] == 6 and progress["students"] == 1
    assert progress["experts"] == [{"rater": "Rater 1", "rated": 0, "completed": False}]
