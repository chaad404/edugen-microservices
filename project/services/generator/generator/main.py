"""
HTTP side of the Generator: health, readiness and the model catalog. The real work arrives through
RabbitMQ (messaging.JobConsumer), so this service has no endpoint that generates questions on request.
"""
import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from . import __version__, config
from .catalog import load_catalog
from .evaluator_client import EvaluatorClient
from .jobs import JobHandler, Runtime
from .messaging import JobConsumer
from .strategies import DESCRIPTIONS

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(runtime: Optional[Runtime] = None, *, start_worker: bool = config.RUN_WORKER) -> FastAPI:
    if runtime is None:
        runtime = Runtime(load_catalog(config.MODELS_FILE), EvaluatorClient(config.EVALUATOR_URL),
                          max_attempts=config.MAX_ATTEMPTS, simulator_delay=config.SIMULATOR_DELAY,
                          llm_timeout=config.LLM_READ_TIMEOUT)
    consumer = JobConsumer(config.RABBITMQ_URL, JobHandler(runtime)) if start_worker else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if consumer is not None:
            threading.Thread(target=consumer.run_forever, name="job-consumer", daemon=True).start()
        yield
        if consumer is not None:
            consumer.stop()

    app = FastAPI(title="EduGen Generator", version=__version__, lifespan=lifespan,
                  description="Consumes generation jobs from RabbitMQ and calls the language models.")

    @app.get("/health", tags=["operations"], summary="Liveness: the process is running")
    def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["operations"], summary="Readiness: connected to the message broker")
    def ready():
        if consumer is not None and not consumer.connected.is_set():
            return JSONResponse({"type": "about:blank", "title": "Not ready", "status": 503,
                                 "detail": "Not connected to the message broker."},
                                status_code=503, media_type="application/problem+json")
        return {"status": "ready"}

    @app.get("/v1/models", tags=["catalog"], summary="Registered models, their price and availability")
    def models():
        return [spec.public() for spec in runtime.catalog.values()]

    @app.get("/v1/strategies", tags=["catalog"], summary="Generation strategies (thesis conditions)")
    def strategies():
        return [{"key": key, "description": text} for key, text in DESCRIPTIONS.items()]

    return app


app = create_app()
