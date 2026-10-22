"""HTTP API of the Evaluator. Stateless: nothing is stored, so any number of instances can run."""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

from . import __version__, config
from .embedder import Embedder, load_embedder
from .framework import describe
from .problems import install_problem_handlers, problem
from .schemas import EvaluationRequest, EvaluationResponse
from .service import evaluate

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(embedder: Optional[Embedder] = None, *, load_on_startup: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.embedder is None and load_on_startup:
            app.state.embedder = await run_in_threadpool(load_embedder, config.EMBEDDER, config.FASTEMBED_CACHE_DIR)
        yield

    app = FastAPI(
        title="EduGen Evaluator",
        version=__version__,
        description="Deterministic quality metrics for multiple-choice questions: the Three Pillars of the "
                    "thesis framework, their frozen bands and the item-writing checks.",
        lifespan=lifespan,
    )
    app.state.embedder = embedder
    install_problem_handlers(app)

    @app.get("/health", tags=["operations"], summary="Liveness: the process is running")
    def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["operations"], summary="Readiness: the embedding model is loaded")
    def ready(request: Request):
        loaded = request.app.state.embedder
        if loaded is None and config.REQUIRE_DENSE:
            return problem(503, "Not ready", "The embedding model is not loaded, so dense metrics are unavailable.")
        return {"status": "ready", "dense_available": loaded is not None,
                "embedding_model": loaded.model_name if loaded is not None else None}

    @app.get("/v1/framework", tags=["framework"], summary="Pillars, cut points and band labels")
    def framework():
        return describe()

    @app.post("/v1/evaluations", response_model=EvaluationResponse, tags=["evaluation"],
              summary="Score a batch of questions (computed, not stored)")
    def create_evaluation(body: EvaluationRequest, request: Request):
        return evaluate(body, request.app.state.embedder)

    return app


app = create_app()
