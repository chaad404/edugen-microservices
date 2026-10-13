import pytest
from fastapi.testclient import TestClient
from project.services.quiz.src.main import app
from project.services.quiz.src.database import Base, engine

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield

def test_quiz_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "edugen-quiz"

def test_create_and_take_exam():
    payload = {
        "title": "Systems Engineering Quiz 1",
        "domain": "SYSTEM",
        "duration_minutes": 15,
        "passing_percentage": 50.0,
        "questions": [
            {
                "question_stem": "What is the transfer function H(s)?",
                "option_a": "Output Laplace transform / Input Laplace transform",
                "option_b": "State matrix A determinant",
                "option_c": "Time derivative of input signal",
                "option_d": "Inverse Fourier transform of impulse",
                "correct_option": "A",
                "explanation": "H(s) = Y(s)/X(s)."
            },
            {
                "question_stem": "Which element provides feedback in closed loop?",
                "option_a": "Sensor",
                "option_b": "Actuator",
                "option_c": "Process",
                "option_d": "Disturbance",
                "correct_option": "A",
                "explanation": "Sensor measures output to compare with setpoint."
            }
        ]
    }
    create_res = client.post("/exams", json=payload)
    assert create_res.status_code == 200
    exam_id = create_res.json()["exam_id"]

    # Student requests exam
    take_res = client.get(f"/exams/{exam_id}/take")
    assert take_res.status_code == 200
    data = take_res.json()
    assert data["total_questions"] == 2
    assert len(data["questions"]) == 2

    # Verify security: keys and explanations are stripped!
    for q in data["questions"]:
        assert "correct_option" not in q
        assert "explanation" not in q

def test_submit_and_grade_exam():
    # Create an exam
    payload = {
        "title": "Networking Quick Quiz",
        "domain": "NETCOMP",
        "duration_minutes": 10,
        "passing_percentage": 50.0,
        "questions": [
            {
                "question_stem": "TCP operates at which OSI layer?",
                "option_a": "Transport layer",
                "option_b": "Network layer",
                "option_c": "Data link layer",
                "option_d": "Application layer",
                "correct_option": "A"
            }
        ]
    }
    exam_id = client.post("/exams", json=payload).json()["exam_id"]
    take_data = client.get(f"/exams/{exam_id}/take").json()
    q_id = take_data["questions"][0]["id"]

    # Student 1 submits correct answer
    sub_res = client.post(f"/exams/{exam_id}/submit", json={
        "student_name": "Alice",
        "answers": {q_id: "A"}
    })
    assert sub_res.status_code == 200
    res_data = sub_res.json()
    assert res_data["score_percentage"] == 100.0
    assert res_data["passed"] is True

    # Student 2 submits wrong answer
    sub_res2 = client.post(f"/exams/{exam_id}/submit", json={
        "student_name": "Bob",
        "answers": {q_id: "B"}
    })
    assert sub_res2.status_code == 200
    assert sub_res2.json()["score_percentage"] == 0.0

    # Check analytics
    analytics_res = client.get(f"/exams/{exam_id}/analytics")
    assert analytics_res.status_code == 200
    analytics = analytics_res.json()
    assert analytics["total_attempts"] == 2
    assert analytics["average_score"] == 50.0
    assert analytics["pass_rate"] == 50.0

    item_stat = analytics["items"][0]
    assert item_stat["total_attempts"] == 2
    assert item_stat["correct_count"] == 1
    assert item_stat["difficulty_index_p"] == 0.5
    assert item_stat["option_selection_counts"]["A"] == 1
    assert item_stat["option_selection_counts"]["B"] == 1
