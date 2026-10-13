import os
import json
import httpx
from typing import List, Tuple
from .base import BaseLLMProvider
from ..schemas import GenerateBatchRequest, GeneratedMCQ

SYSTEM_PROMPT = """You are an expert computer engineering professor.
Your task is to generate high-quality multiple-choice questions (MCQs) strictly grounded in the provided syllabus text.
Each question must contain:
- question_stem: clear, unambiguous problem statement
- option_a, option_b, option_c, option_d: 4 realistic technical choices
- correct_option: exactly one letter (A, B, C, or D)
- explanation: technical justification

Return STRICT JSON matching:
{
  "questions": [
     {
       "question_stem": "...",
       "option_a": "...",
       "option_b": "...",
       "option_c": "...",
       "option_d": "...",
       "correct_option": "A",
       "explanation": "..."
     }
  ]
}
"""

class OpenAIProvider(BaseLLMProvider):
    """Live LLM provider communicating with OpenAI or OpenAI-compatible endpoints."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def generate(self, req: GenerateBatchRequest) -> Tuple[List[GeneratedMCQ], int, float]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not configured.")

        user_content = f"""TOPIC: {req.title} ({req.topic_id})
CURRICULUM REFERENCE TEXT:
{req.source_text[:3000]}

Generate {req.count} questions based strictly on the text above."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-4o" if "gpt" in req.model_name.lower() else "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        raw_questions = parsed.get("questions", [])

        questions = []
        for q in raw_questions[:req.count]:
            item = GeneratedMCQ(
                question_stem=q["question_stem"],
                option_a=q["option_a"],
                option_b=q["option_b"],
                option_c=q["option_c"],
                option_d=q["option_d"],
                correct_option=q["correct_option"].upper(),
                explanation=q.get("explanation"),
                strategy_used=req.strategy
            )
            questions.append(item)

        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", req.count * 400)
        cost = round((usage.get("prompt_tokens", 0) * 0.005 + usage.get("completion_tokens", 0) * 0.015) / 1000.0, 5)

        return questions, tokens, cost
