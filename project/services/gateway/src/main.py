import asyncio
import json
import uuid
from typing import Dict, Any, List
import httpx
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import GENERATOR_URL, EVALUATOR_URL, QUIZ_URL
from .auth import create_access_token, get_current_user

app = FastAPI(
    title="EduGen API Gateway & Orchestrator",
    description="Central API Gateway, JWT security, SSE streaming, and microservice orchestrator",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for active runs and SSE event queues
RUNS_STORE: Dict[str, Dict[str, Any]] = {}
RUN_EVENT_QUEUES: Dict[str, asyncio.Queue] = {}

# Sample curriculum topics
CURRICULUM_TOPICS = [
    {
        "topic_id": "SYSTEM-2022-1",
        "domain": "SYSTEM",
        "title": "Systems Fundamentals and Control Loop Basics",
        "description": "Linear time-invariant (LTI) systems, transfer functions H(s), state-space representations, and closed-loop feedback.",
        "source_text": "In linear time-invariant (LTI) systems, the transfer function H(s) is the ratio of output Laplace transform Y(s) to input X(s). State-space equations use state matrix A, input matrix B, output matrix C, and feedthrough matrix D: x'(t) = Ax(t) + Bu(t), y(t) = Cx(t) + Du(t). Closed-loop control relies on feedback sensors comparing output to setpoint."
    },
    {
        "topic_id": "NETCOMP-2022-3",
        "domain": "NETCOMP",
        "title": "TCP Congestion Control & Flow Control",
        "description": "Slow Start, Congestion Avoidance, Fast Retransmit (triple duplicate ACKs), and ssthresh transitions.",
        "source_text": "TCP congestion control operates four algorithms: Slow Start, Congestion Avoidance, Fast Retransmit, and Fast Recovery. When cwnd reaches the slow start threshold (ssthresh), exponential growth transitions to linear growth. Fast Retransmit triggers upon receiving three duplicate ACKs without waiting for RTO timeout."
    },
    {
        "topic_id": "SPECALK-2022-2",
        "domain": "SPECALK",
        "title": "Graph Algorithms and Dynamic Programming",
        "description": "Shortest path algorithms (Dijkstra non-negative weights vs. Bellman-Ford), and optimal substructure.",
        "source_text": "Dijkstra's single-source shortest path algorithm requires non-negative edge weights to guarantee correctness with greedy relaxation. Bellman-Ford accommodates negative edge weights and detects negative cycles in O(V*E) time. Dynamic programming solves problems exhibiting optimal substructure and overlapping subproblems."
    }
]

class LoginRequest(BaseModel):
    username: str
    role: str = "instructor"  # "instructor" or "student"

class TriggerRunRequest(BaseModel):
    topic_id: str
    source_text: str
    domain: str = "SYSTEM"
    title: str = "Technical Assessment"
    model_name: str = "mock"
    strategy: str = "multi_agent"
    count: int = 3

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "edugen-gateway",
        "version": "1.0.0",
        "downstream": {
            "generator": GENERATOR_URL,
            "evaluator": EVALUATOR_URL,
            "quiz": QUIZ_URL
        }
    }

@app.post("/api/auth/login")
def login_endpoint(req: LoginRequest):
    token = create_access_token(user_id=req.username, role=req.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": req.username,
        "role": req.role
    }

@app.get("/api/topics")
def list_topics_endpoint():
    return CURRICULUM_TOPICS

async def push_run_event(run_id: str, event_type: str, data: Any):
    if run_id in RUN_EVENT_QUEUES:
        packet = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        await RUN_EVENT_QUEUES[run_id].put(packet)

@app.post("/api/runs")
async def trigger_run_endpoint(req: TriggerRunRequest, current_user: dict = Depends(get_current_user)):
    run_id = str(uuid.uuid4())
    RUN_EVENT_QUEUES[run_id] = asyncio.Queue()

    # Initial state
    run_state = {
        "run_id": run_id,
        "topic_id": req.topic_id,
        "domain": req.domain,
        "title": req.title,
        "status": "INITIALIZING",
        "model_name": req.model_name,
        "strategy": req.strategy,
        "questions": [],
        "metrics_summary": {}
    }
    RUNS_STORE[run_id] = run_state

    # Execute pipeline asynchronously in background task
    async def run_pipeline():
        try:
            await push_run_event(run_id, "status_update", {"status": "GENERATING", "step": 1})
            
            # Step 1: Call Service 2 (Generator)
            gen_payload = {
                "topic_id": req.topic_id,
                "domain": req.domain,
                "title": req.title,
                "source_text": req.source_text,
                "model_name": req.model_name,
                "strategy": req.strategy,
                "count": req.count
            }

            async with httpx.AsyncClient(timeout=45.0) as client:
                gen_resp = await client.post(f"{GENERATOR_URL}/generate/batch", json=gen_payload)
                gen_resp.raise_for_status()
                gen_data = gen_resp.json()

            generated_questions = gen_data["questions"]
            await push_run_event(run_id, "status_update", {
                "status": "EVALUATING", 
                "step": 2, 
                "question_count": len(generated_questions)
            })

            # Step 2: Call Service 3 (Evaluator)
            eval_payload = {
                "source_text": req.source_text,
                "questions": generated_questions
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                eval_resp = await client.post(f"{EVALUATOR_URL}/evaluate/batch", json=eval_payload)
                eval_resp.raise_for_status()
                eval_data = eval_resp.json()

            # Merge questions with their Three Pillars scores
            merged_items = []
            for q, m in zip(generated_questions, eval_data["results"]):
                merged_items.append({
                    **q,
                    "metrics": m
                })

            # Complete Run
            RUNS_STORE[run_id]["status"] = "COMPLETED"
            RUNS_STORE[run_id]["questions"] = merged_items
            RUNS_STORE[run_id]["metrics_summary"] = {
                "mean_semantic_alignment": eval_data["mean_semantic_alignment"],
                "mean_linguistic_complexity": eval_data["mean_linguistic_complexity"],
                "mean_distractor_plausibility": eval_data["mean_distractor_plausibility"],
                "passed_quality_gate_count": eval_data["passed_quality_gate_count"],
                "latency_seconds": gen_data.get("latency_seconds", 0.0),
                "tokens_used": gen_data.get("tokens_used", 0)
            }

            await push_run_event(run_id, "batch_completed", RUNS_STORE[run_id])
        except Exception as e:
            RUNS_STORE[run_id]["status"] = "FAILED"
            RUNS_STORE[run_id]["error"] = str(e)
            await push_run_event(run_id, "error", {"error": str(e)})

    asyncio.create_task(run_pipeline())

    return {
        "run_id": run_id,
        "status": "INITIALIZING",
        "stream_url": f"/api/runs/{run_id}/stream"
    }

@app.get("/api/runs/{run_id}")
def get_run_endpoint(run_id: str):
    if run_id not in RUNS_STORE:
        raise HTTPException(status_code=404, detail="Run not found")
    return RUNS_STORE[run_id]

@app.get("/api/runs/{run_id}/stream")
async def stream_run_endpoint(run_id: str):
    if run_id not in RUN_EVENT_QUEUES:
        raise HTTPException(status_code=404, detail="Run stream not found")

    queue = RUN_EVENT_QUEUES[run_id]

    async def event_generator():
        try:
            while True:
                packet = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield packet
                if "batch_completed" in packet or "error" in packet:
                    break
        except asyncio.TimeoutError:
            yield "event: ping\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- PROXY ENDPOINTS TO SERVICE 4 (QUIZ) ---
@app.post("/api/exams/publish")
async def publish_exam_endpoint(payload: Dict[str, Any]):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{QUIZ_URL}/exams", json=payload)
        return resp.json()

@app.get("/api/exams")
async def list_exams_proxy():
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{QUIZ_URL}/exams")
        return resp.json()

@app.get("/api/exams/{exam_id}/take")
async def take_exam_proxy(exam_id: str):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{QUIZ_URL}/exams/{exam_id}/take")
        return resp.json()

@app.post("/api/exams/{exam_id}/submit")
async def submit_exam_proxy(exam_id: str, payload: Dict[str, Any]):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{QUIZ_URL}/exams/{exam_id}/submit", json=payload)
        return resp.json()

@app.get("/api/exams/{exam_id}/analytics")
async def exam_analytics_proxy(exam_id: str):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{QUIZ_URL}/exams/{exam_id}/analytics")
        return resp.json()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("project.services.gateway.src.main:app", host="0.0.0.0", port=8000, reload=True)
