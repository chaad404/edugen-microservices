import hashlib
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient

from evaluator.embedder import normalize
from evaluator.main import create_app


class FakeEmbedder:
    """Deterministic bag-of-words vectors: texts that share words get a high cosine. No model download."""
    model_name = "fake-bag-of-words"

    def embed(self, texts):
        out = np.zeros((len(texts), 256), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % 256] += 1.0
        return normalize(out)


SOURCE = (
    "TCP congestion control uses slow start, congestion avoidance, fast retransmit and fast recovery.\n\n"
    "During slow start the congestion window grows exponentially until it reaches the slow start threshold.\n\n"
    "Three duplicate acknowledgements trigger fast retransmit of the missing segment without waiting for a timeout."
)

ITEM = {
    "id": "q1",
    "question": "What happens to the TCP congestion window during slow start before it reaches the slow start threshold?",
    "options": {
        "A": "It grows exponentially with every round trip until the threshold is reached",
        "B": "It grows linearly by one segment per round trip from the beginning",
        "C": "It stays constant until three duplicate acknowledgements arrive",
        "D": "It is halved after every acknowledged segment to avoid congestion",
    },
    "answer": "A",
}


@pytest.fixture
def client():
    return TestClient(create_app(FakeEmbedder()))


@pytest.fixture
def lexical_client():
    return TestClient(create_app(None, load_on_startup=False))
