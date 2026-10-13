import pytest
from fastapi.testclient import TestClient
from project.services.gateway.src.main import app

client = TestClient(app)

def test_gateway_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "edugen-gateway"

def test_auth_login():
    res = client.post("/api/auth/login", json={"username": "Prof_Laborci", "role": "instructor"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["username"] == "Prof_Laborci"
    assert data["role"] == "instructor"

def test_list_topics():
    res = client.get("/api/topics")
    assert res.status_code == 200
    topics = res.json()
    assert len(topics) >= 3
    assert any(t["domain"] == "SYSTEM" for t in topics)
    assert any(t["domain"] == "NETCOMP" for t in topics)
