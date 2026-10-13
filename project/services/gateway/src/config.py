import os

GENERATOR_URL = os.getenv("GENERATOR_URL", "http://localhost:8001")
EVALUATOR_URL = os.getenv("EVALUATOR_URL", "http://localhost:8002")
QUIZ_URL = os.getenv("QUIZ_URL", "http://localhost:8003")

JWT_SECRET = os.getenv("JWT_SECRET", "edugen-secret-key-za0p52-programming5-secure-token-2026")
JWT_ALGORITHM = "HS256"
