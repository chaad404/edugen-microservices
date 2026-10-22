"""HTTP API of the Lab and the start-up of its background workers."""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from . import __version__, config
from .clients import EvaluatorClient, FrameworkCache, GeneratorClient, ReviewClient
from .db import make_engine, make_session_factory
from .models import Base
from .problems import install_problem_handlers
from .routes import auth, catalog, events, experiments, ops, studies
from .seed import import_thesis_sample, seed_demo_topics
from .workers import Workers

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def prepare_database(session_factory: sessionmaker, run_seed: bool = True) -> None:
    Base.metadata.create_all(session_factory.kw["bind"])
    if run_seed:
        with session_factory() as session:
            added = seed_demo_topics(session, config.SEED_DIR / "demo_topics.json")
            imported = import_thesis_sample(session, config.THESIS_SAMPLE_FILE)
            session.commit()
        logger.info("Seed: %d demo topics added, thesis sample %s", added, "imported" if imported else "already present")


def create_app(*, session_factory: Optional[sessionmaker] = None, evaluator: Optional[EvaluatorClient] = None,
               generator: Optional[GeneratorClient] = None, review: Optional[ReviewClient] = None,
               start_workers: Optional[bool] = None, run_seed: bool = True) -> FastAPI:
    config.warn_about_defaults()
    session_factory = session_factory or make_session_factory(make_engine(config.DATABASE_URL))
    evaluator = evaluator or EvaluatorClient(config.EVALUATOR_URL)
    workers = None
    if config.RUN_WORKERS if start_workers is None else start_workers:
        workers = Workers(session_factory, evaluator, config.RABBITMQ_URL)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_in_threadpool(prepare_database, session_factory, run_seed)
        if workers is not None:
            workers.start()
        yield
        if workers is not None:
            workers.shutdown()

    app = FastAPI(
        title="EduGen Lab", version=__version__, root_path=config.ROOT_PATH, lifespan=lifespan,
        description="Experiments comparing language models on exam-question generation: topics, jobs, generated "
                    "questions, their scores, comparisons, and blind human-evaluation studies.",
    )
    app.state.session_factory = session_factory
    app.state.evaluator = evaluator
    app.state.generator = generator or GeneratorClient(config.GENERATOR_URL)
    app.state.review = review or ReviewClient(config.REVIEW_URL)
    app.state.framework = FrameworkCache(evaluator)
    app.state.stream_max_seconds = 900.0
    install_problem_handlers(app)
    for module in (ops, auth, catalog, experiments, studies, events):
        app.include_router(module.router)
    return app


app = create_app()
