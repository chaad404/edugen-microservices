"""
Offline stand-in for a language model, so the whole pipeline can be demonstrated without API keys or cost.

It reads the same prompts a real model gets and answers in the same JSON format, but its questions are
synthetic cloze items ("which term completes this statement") built from sentences of the context. Results
are always marked as simulated; they are never presented as the output of a real model.
"""
import hashlib
import json
import random
import re
import time
from typing import Callable

from ..catalog import ModelSpec
from .base import ChatResult

LABELS = ("A", "B", "C", "D")
_STOPWORDS = {"about", "after", "again", "against", "because", "before", "being", "below", "between", "could",
              "during", "every", "further", "having", "other", "should", "their", "there", "these", "those",
              "through", "under", "until", "which", "while", "would", "where", "whether", "within", "without"}


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16))


def _context(prompt: str) -> str:
    match = re.search(r"<context>\n?(.*?)\n?</context>", prompt, flags=re.S)
    if match:
        return match.group(1)
    return prompt.rsplit("\n\nContext: ", 1)[-1]


def _sentences(context: str) -> list[str]:
    lines = [line for line in context.splitlines() if not line.lstrip().startswith("#")]
    text = " ".join(lines)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 8 <= len(s.split()) <= 40]


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z-]{4,}", text) if w.lower() not in _STOPWORDS]


class SimulatorProvider:
    name = "simulator"

    def __init__(self, spec: ModelSpec, delay: float = 0.0, sleep: Callable[[float], None] = time.sleep):
        self.spec = spec
        self.delay = delay
        self.sleep = sleep

    def chat(self, messages: list[dict], json_mode: bool) -> ChatResult:
        prompt = messages[-1]["content"]
        rng = _rng(prompt)
        if self.delay:
            self.sleep(self.delay * rng.uniform(0.5, 1.5))
        payload = self._repair(prompt, rng) if "QUESTIONS TO REVISE:" in prompt else self._write(prompt, rng)
        text = json.dumps(payload, ensure_ascii=False)
        return ChatResult(text, len(prompt) // 4, len(text) // 4, self.spec.model_id)

    def _write(self, prompt: str, rng: random.Random) -> dict:
        match = re.search(r"\b(?:Write|generate) (\d+)\b", prompt)
        count = int(match.group(1)) if match else 5
        context = _context(prompt)
        vocabulary = sorted(set(_content_words(context)), key=str.lower)
        sentences = _sentences(context)
        rng.shuffle(sentences)

        questions, used_keys = [], set()
        for sentence in sentences:
            candidates = [w for w in _content_words(sentence) if w.lower() not in used_keys]
            if not candidates:
                continue
            key = max(candidates, key=len)
            in_sentence = {w.lower() for w in _content_words(sentence)}
            pool = [w for w in vocabulary if w.lower() not in in_sentence and abs(len(w) - len(key)) <= 3]
            pool = list(dict.fromkeys(w.lower() for w in pool))
            if len(pool) < 3:
                continue
            distractors = rng.sample(pool, 3)
            blanked = re.sub(rf"\b{re.escape(key)}\b", "____", sentence, count=1)
            texts = [key.lower()] + distractors
            rng.shuffle(texts)
            options = dict(zip(LABELS, texts))
            answer = next(label for label, text in options.items() if text == key.lower())
            questions.append({"question": f'Which term correctly completes this statement: "{blanked}"',
                              "options": options, "answer": answer, "evidence": sentence})
            used_keys.add(key.lower())
            if len(questions) == count:
                break
        return {"questions": questions}

    def _repair(self, prompt: str, rng: random.Random) -> dict:
        """Rewrites the options the repair instructions name, using other terms from the context."""
        vocabulary = list(dict.fromkeys(w.lower() for w in _content_words(_context(prompt))))
        section = prompt.split("QUESTIONS TO REVISE:", 1)[1].split("\n\nReturn one JSON object", 1)[0]
        revised = []
        for block in re.split(r"\n*Question \d+:\n", section)[1:]:
            item_text, _, problems = block.partition("\nProblems:\n")
            item = json.loads(item_text)
            targets = set(re.findall(r"Rewrite ([A-D])\b", problems)) - {item["answer"]}
            taken = {v.lower() for v in item["options"].values()}
            for label in sorted(targets):
                fresh = [w for w in vocabulary if w not in taken]
                if fresh:
                    item["options"][label] = rng.choice(fresh)
                    taken.add(item["options"][label])
            revised.append(item)
        return {"questions": revised}
