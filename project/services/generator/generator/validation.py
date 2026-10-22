"""
Canonical MCQ shape, structural validation and tolerant JSON parsing of model output
(ported from the thesis, src/utils/validators.py). The Evaluator validates again on its side:
each service checks its own inputs.
"""
import json
import re

LABELS = ("A", "B", "C", "D")
ANSWER_KEYS = ("answer", "correct_answer", "correct_option")
BANNED_PHRASES = ("based on the context", "provided text", "according to the passage")


class InvalidOutput(ValueError):
    """The model answered, but not with usable questions."""


def parse_json_object(text: str) -> dict:
    """Parses a JSON object, tolerating Markdown code fences and text around the object."""
    cleaned = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise InvalidOutput("The model output contains no JSON object.") from None
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as e:
            raise InvalidOutput(f"The model output is not valid JSON: {e.msg}") from None
    if not isinstance(data, dict):
        raise InvalidOutput("The model output is not a JSON object.")
    return data


def _normalize_answer_label(value, options):
    text = str(value).strip()
    if isinstance(options, dict):
        hits = [k for k, v in options.items() if str(v).strip().lower() == text.lower()]
        if len(hits) == 1:
            return hits[0]
    match = re.match(r"^([A-Da-d])(?:$|[).:])", text)
    return match.group(1).upper() if match else text


def normalize_mcq(item):
    if not isinstance(item, dict):
        return item
    out = dict(item)
    if "question" not in out and "question_stem" in out:
        out["question"] = out.pop("question_stem")
    options = out.get("options")
    if isinstance(options, list) and len(options) == 4:
        out["options"] = dict(zip(LABELS, options))
    for key in ANSWER_KEYS:
        if out.get(key) is not None:
            out["answer"] = _normalize_answer_label(out[key], out.get("options"))
            break
    for key in ANSWER_KEYS[1:]:
        out.pop(key, None)
    return out


def validate_single_mcq(data) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "MCQ item is not an object."
    for key in ("question", "options", "answer"):
        if key not in data:
            return False, f"Missing required key: {key}"
    options = data["options"]
    if not isinstance(options, dict) or len(options) != 4 or any(label not in options for label in LABELS):
        return False, "Options must be an object with the labels A, B, C and D."
    if any(not str(options[label]).strip() for label in LABELS):
        return False, "An option is empty."
    if len({str(v).strip().lower() for v in options.values()}) != 4:
        return False, "Duplicate option content detected."
    if any(not 2 <= len(str(v)) <= 256 for v in options.values()):
        return False, "An option has an implausible length."
    stem = str(data["question"]).strip()
    if len(stem.split()) < 3:
        return False, "Question stem is too short (less than 3 words)."
    if any(phrase in stem.lower() for phrase in BANNED_PHRASES):
        return False, "Question stem contains a filler phrase."
    if data["answer"] not in LABELS:
        return False, f"Invalid answer label: {data['answer']}"
    return True, "Valid"


def normalized_questions(data: dict, expected: int) -> list[dict]:
    """The validated questions of a {"questions": [...]} payload, or InvalidOutput saying why not."""
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise InvalidOutput("Output missing the 'questions' array.")
    if len(questions) != expected:
        raise InvalidOutput(f"Expected {expected} questions, got {len(questions)}.")
    out = []
    for i, raw in enumerate(questions, 1):
        item = normalize_mcq(raw)
        ok, message = validate_single_mcq(item)
        if not ok:
            raise InvalidOutput(f"Question {i} invalid: {message}")
        clean = {"question": str(item["question"]).strip(),
                 "options": {label: str(item["options"][label]).strip() for label in LABELS},
                 "answer": item["answer"]}
        if item.get("evidence"):
            clean["evidence"] = str(item["evidence"]).strip()
        out.append(clean)
    return out
