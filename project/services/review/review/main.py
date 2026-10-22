"""HTTP API of the Review service and its outbox relay."""
import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from . import __version__, config
from .broker import RabbitPublisher
from .db import make_engine, make_session_factory
from .models import Base
from .outbox import OutboxRelay
from .problems import install_problem_handlers
from .routes import internal, ops, public

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(*, session_factory: Optional[sessionmaker] = None, start_workers: Optional[bool] = None) -> FastAPI:
    config.warn_about_defaults()
    session_factory = session_factory or make_session_factory(make_engine(config.DATABASE_URL))
    stop = threading.Event()
    run_relay = config.RUN_WORKERS if start_workers is None else start_workers

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_in_threadpool(Base.metadata.create_all, session_factory.kw["bind"])
        if run_relay:
            relay = OutboxRelay(session_factory, RabbitPublisher(config.RABBITMQ_URL))
            threading.Thread(target=relay.run_forever, args=(stop,), name="outbox-relay", daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="EduGen Review", version=__version__, root_path=config.ROOT_PATH, lifespan=lifespan,
                  description="Blind expert review and anonymous student quizzes of generated questions. "
                              "This service never learns which model wrote a question.")
    app.state.session_factory = session_factory
    install_problem_handlers(app)
    for router in (ops, internal, public):
        app.include_router(router)
    return app


app = create_app()
