from datetime import timedelta

import jwt

from lab import config
from lab.security import issue_token


def test_login_returns_a_bearer_token(client):
    response = client.post("/auth/login", json={"username": "operator", "password": "edugen-demo"})
    assert response.status_code == 200
    body = response.json()
    claims = jwt.decode(body["access_token"], config.JWT_SECRET, algorithms=["HS256"], audience="edugen")
    assert claims["iss"] == "edugen-lab" and claims["role"] == "operator" and body["token_type"] == "bearer"


def test_wrong_credentials_are_a_problem_response(client):
    response = client.post("/auth/login", json={"username": "operator", "password": "nope"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_routes_need_a_valid_operator_token(client, auth):
    assert client.get("/topics").status_code == 401
    assert client.get("/topics", headers=auth).status_code == 200
    expired = issue_token("operator", ttl=timedelta(seconds=-5))
    assert client.get("/topics", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    forged = jwt.encode({"iss": "edugen-lab", "aud": "edugen", "sub": "x", "role": "operator", "iat": 0,
                         "exp": 9999999999}, "another-secret-that-is-long-enough", algorithm="HS256")
    assert client.get("/topics", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_a_token_for_another_audience_or_role_is_rejected(client):
    stream_ticket = issue_token("operator", audience="edugen-lab-stream")
    assert client.get("/topics", headers={"Authorization": f"Bearer {stream_ticket}"}).status_code == 401
    student = jwt.encode({"iss": "edugen-lab", "aud": "edugen", "sub": "s", "role": "student", "iat": 0,
                          "exp": 9999999999}, config.JWT_SECRET, algorithm="HS256")
    assert client.get("/topics", headers={"Authorization": f"Bearer {student}"}).status_code == 403


def test_stream_tickets_are_bound_to_one_channel(client, auth):
    channel = "experiment:2026a5e0-0000-4000-8000-000000000001"
    body = client.post("/auth/stream-tickets", json={"channel": channel}, headers=auth).json()
    other = "experiment:2026a5e0-0000-4000-8000-000000000002"
    response = client.get(f"/events/stream?channel={other}&ticket={body['ticket']}")
    assert response.status_code == 403
    assert client.post("/auth/stream-tickets", json={"channel": "anything"}, headers=auth).status_code == 422
