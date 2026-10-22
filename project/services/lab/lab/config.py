"""Settings from environment variables. Development defaults are logged as warnings at start-up."""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lab.db")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F?heartbeat=60")
EVALUATOR_URL = os.getenv("EVALUATOR_URL", "http://localhost:8002")
GENERATOR_URL = os.getenv("GENERATOR_URL", "http://localhost:8001")
REVIEW_URL = os.getenv("REVIEW_URL", "http://localhost:8003")

JWT_SECRET = os.getenv("LAB_JWT_SECRET", "dev-only-lab-secret-change-me-0123456789")
TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", "480"))
STREAM_TICKET_TTL_SECONDS = int(os.getenv("STREAM_TICKET_TTL_SECONDS", "300"))
OPERATOR_USERNAME = os.getenv("OPERATOR_USERNAME", "operator")
OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD", "edugen-demo")

SEED_DIR = Path(os.getenv("SEED_DIR", str(Path(__file__).resolve().parents[1] / "seed")))
# The public sample by default; point it at a local full export (never committed) to compare all topics
THESIS_SAMPLE_FILE = Path(os.getenv("THESIS_SAMPLE_FILE", str(SEED_DIR / "thesis_sample.json")))
RUN_WORKERS = os.getenv("RUN_WORKERS", "true").lower() == "true"
ROOT_PATH = os.getenv("ROOT_PATH", "")  # "/api/lab" behind the gateway, so the OpenAPI page works there
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def warn_about_defaults() -> None:
    if "LAB_JWT_SECRET" not in os.environ:
        logger.warning("LAB_JWT_SECRET is not set: using the development default. Set it outside local demos.")
    if "OPERATOR_PASSWORD" not in os.environ:
        logger.warning("OPERATOR_PASSWORD is not set: using the development default 'edugen-demo'.")
