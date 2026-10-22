from conftest import ITEM, SOURCE


def test_health_and_framework(client):
    assert client.get("/health").json() == {"status": "ok"}
    framework = client.get("/v1/framework").json()
    assert framework["version"] == "thesis-2026-10"
    assert len(framework["pillars"]) == 4


def test_evaluation_returns_metrics_bands_and_batch_checks(client):
    response = client.post("/v1/evaluations", json={"source_text": SOURCE, "items": [ITEM]})
    assert response.status_code == 200
    body = response.json()
    assert body["dense_available"] is True
    result = body["items"][0]
    assert result["id"] == "q1" and result["valid"] is True
    for metric in ("alignment", "alignment_lexical", "grade", "plausibility", "plausibility_lexical", "diversity"):
        assert result["metrics"][metric] is not None
    assert set(result["bands"]) == {"P1", "P2", "P3a", "P3b"}
    assert body["batch"]["n"] == 1 and body["batch"]["key_positions"]["A"] == 1


def test_invalid_items_are_reported_not_scored(client):
    broken = {**ITEM, "id": "bad", "options": {"A": "one", "B": "two", "C": "three"}}
    body = client.post("/v1/evaluations", json={"source_text": SOURCE, "items": [ITEM, broken]}).json()
    bad = body["items"][1]
    assert bad["valid"] is False and bad["flags"] == ["invalid_schema"] and bad["serious"] is True
    assert body["batch"]["n"] == 1


def test_without_source_text_alignment_is_not_measured(client):
    result = client.post("/v1/evaluations", json={"items": [ITEM]}).json()["items"][0]
    assert result["metrics"]["alignment"] is None and result["bands"]["P1"] is None
    assert result["metrics"]["plausibility"] is not None
    assert result["quality"] is None


def test_without_the_embedding_model_dense_metrics_are_unavailable_not_substituted(lexical_client):
    body = lexical_client.post("/v1/evaluations", json={"source_text": SOURCE, "items": [ITEM]}).json()
    result = body["items"][0]
    assert body["dense_available"] is False
    assert result["metrics"]["alignment"] is None and result["metrics"]["plausibility"] is None
    assert result["metrics"]["alignment_lexical"] is not None
    assert result["bands"]["P2"] is not None and result["bands"]["P1"] is None
    ready = lexical_client.get("/ready")
    assert ready.status_code == 503
    assert ready.headers["content-type"].startswith("application/problem+json")


def test_contract_violations_are_problem_details(client):
    response = client.post("/v1/evaluations", json={"items": []})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Invalid request"

    too_many = client.post("/v1/evaluations", json={"items": [ITEM] * 101})
    assert too_many.status_code == 422
