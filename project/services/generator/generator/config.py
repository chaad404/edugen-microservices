"""Settings from environment variables. API keys are read only where a provider is built."""
import os
from pathlib import Path

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F?heartbeat=60")
EVALUATOR_URL = os.getenv("EVALUATOR_URL", "http://localhost:8002")
MODELS_FILE = os.getenv("MODELS_FILE", str(Path(__file__).with_name("models.yaml")))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "4"))
LLM_READ_TIMEOUT = float(os.getenv("LLM_READ_TIMEOUT_SECONDS", "120"))
# The simulator answers instantly; a short pause makes the live progress visible in demos
SIMULATOR_DELAY = float(os.getenv("SIMULATOR_DELAY_SECONDS", "1.5"))
RUN_WORKER = os.getenv("RUN_WORKER", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
