"""Canonical MCQ shape and structural validation (ported from the thesis, src/utils/validators.py)."""
import re

LABELS = ("A", "B", "C", "D")
ANSWER_KEYS = ("answer", "correct_answer", "correct_option")
BANNED_PHRASES = ("based on the context", "provided text", "according to the passage")


def _normalize_answer_label(value, options):
    """Accepts "B", "b", "B)", "B. text" or the exact text of one option; anything else is left for validation."""
    text = str(value).strip()
    # Exact option text first: "A router forwards..." must not be read as label "A"
    if isinstance(options, dict):
        hits = [k for k, v in options.items() if str(v).strip().lower() == text.lower()]
        if len(hits) == 1:
            return hits[0]
    match = re.match(r"^([A-Da-d])(?:$|[).:])", text)
    return match.group(1).upper() if match else text


def normalize_mcq(item):
    """Maps the shapes models produce onto {"question", "options": {A-D}, "answer"}. Nothing is invented."""
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
    if not isinstance(options, dict) or len(options) != 4:
        return False, "Options must be an object with 4 entries."
    for label in LABELS:
        if label not in options:
            return False, f"Missing option label: {label}"
        if not str(options[label]).strip():
            return False, f"Option {label} is empty."
    if len({str(v).strip().lower() for v in options.values()}) != 4:
        return False, "Duplicate option content detected."
    for label, value in options.items():
        if not 2 <= len(str(value)) <= 256:
            return False, f"Option {label} has implausible length ({len(str(value))} chars)."

    stem = str(data["question"]).strip()
    if len(stem.split()) < 3:
        return False, "Question stem is too short (less than 3 words)."
    for phrase in BANNED_PHRASES:
        if phrase in stem.lower():
            return False, f"Question stem contains a filler phrase: '{phrase}'"
    if data["answer"] not in LABELS:
        return False, f"Invalid answer label: {data['answer']}"
    return True, "Valid"
