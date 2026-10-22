"""Settings from environment variables. Development defaults are logged as warnings at start-up."""
import logging
import os

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./review.db")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F?heartbeat=60")
# Operator tokens are issued by the Lab; this service only verifies them
LAB_JWT_SECRET = os.getenv("LAB_JWT_SECRET", "dev-only-lab-secret-change-me-0123456789")
# Participant tokens are issued and verified here only
REVIEW_JWT_SECRET = os.getenv("REVIEW_JWT_SECRET", "dev-only-review-secret-change-me-012345")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
RUN_WORKERS = os.getenv("RUN_WORKERS", "true").lower() == "true"
ROOT_PATH = os.getenv("ROOT_PATH", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def warn_about_defaults() -> None:
    for name in ("LAB_JWT_SECRET", "REVIEW_JWT_SECRET"):
        if name not in os.environ:
            logger.warning("%s is not set: using the development default. Set it outside local demos.", name)
