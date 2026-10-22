"""Settings from environment variables."""
import os

EMBEDDER = os.getenv("EMBEDDER", "fastembed")                  # "fastembed" or "none"
FASTEMBED_CACHE_DIR = os.getenv("FASTEMBED_CACHE_DIR") or None
# Readiness fails without the embedding model, because the framework bands are defined on the dense metrics
REQUIRE_DENSE = os.getenv("REQUIRE_DENSE", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
