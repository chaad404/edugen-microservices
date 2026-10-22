"""
Prompts of the thesis conditions. v1 is the April 2026 baseline template, unchanged (its single example
answer is "A", which is one cause of the key-position bias the thesis found). v2 and the repair prompt come
from the thesis pipeline v2 (docs/pipeline_v2.md).
"""
import json
import re
from pathlib import Path
from typing import Optional, Sequence

_DIR = Path(__file__).with_name("templates")
SYSTEM_V1 = "Output ONLY JSON."
SYSTEM_V2 = ("You are an experienced university examiner who writes high-quality multiple-choice exam "
             "questions. Reply with one valid JSON object only.")

REPAIR_PROMPT = """<context>
{CONTEXT}
</context>

You are revising multiple-choice exam questions written from the context above. Automatic checks found
the problems listed under each question. Fix exactly those problems and nothing else:
- Keep each question's concept, and keep its correct answer correct according to the context.
- Every rewritten distractor must be clearly wrong according to the context, but tempting for a student who
  only half knows the topic. The three distractors must make different mistakes.
- Keep all four options similar in length and grammatical form.
- Update "evidence" if needed: it must be copied word for word from the context and prove the correct answer.

QUESTIONS TO REVISE:
{ITEMS}

Return one JSON object with every question above, in the same order, in this format:
{{"questions": [{{"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, "answer": "<letter>", "evidence": "..."}}]}}
"""


def _template(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")


def v1_messages(source_text: str, num_questions: int) -> list[dict]:
    template = _template("mcq_prompt_v1.txt").replace("{NUM_QUESTIONS}", str(num_questions))
    return [{"role": "system", "content": SYSTEM_V1},
            {"role": "user", "content": f"{template}\n\nContext: {source_text}"}]


def v2_messages(context: str, num_questions: int, focus: Optional[Sequence[str]] = None) -> list[dict]:
    focus_line = ("\nBase this set of questions on these parts of the context: " + "; ".join(focus) + ".\n"
                  if focus else "")
    prompt = (_template("mcq_prompt_v2.txt").replace("{NUM_QUESTIONS}", str(num_questions))
              .replace("{FOCUS}", focus_line).replace("{CONTEXT}", context))
    return [{"role": "system", "content": SYSTEM_V2}, {"role": "user", "content": prompt}]


def section_headings(text: str) -> list[str]:
    """Markdown headings of a topic text ("## Slow start" -> "Slow start")."""
    return [m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.+)$", text, flags=re.M)]


def focus_groups(text: str, groups: int) -> list[Optional[list[str]]]:
    """Splits the headings into contiguous groups, one per Writer call; no focus if there are too few."""
    headings = section_headings(text)
    if len(headings) < groups:
        return [None] * groups
    size = len(headings) / groups
    return [headings[int(i * size):int((i + 1) * size)] for i in range(groups)]


def repair_instructions(item: dict, flags: Sequence[str]) -> list[str]:
    """Plain-language instructions for the repair step, one per flag (ported from the thesis verifier)."""
    key, notes = item["answer"], []
    for flag in flags:
        code, _, labels = flag.partition(":")
        targets = labels.split(",") if labels else []
        if code == "too_close":
            notes += [f"Option {t} says almost the same as the correct answer {key}. Rewrite {t} so it is clearly "
                      f"wrong according to the context, but still tempting." for t in targets]
        elif code == "weak":
            notes += [f"Option {t} is too easy to rule out. Rewrite {t} as a mistake a half-prepared student would "
                      f"make, using the same technical terms as the correct answer." for t in targets]
        elif code == "same_mistake":
            notes.append(f"Options {targets[0]} and {targets[1]} make the same mistake. Rewrite {targets[1]} so it "
                         f"makes a different mistake.")
        elif code == "evidence_supports":
            notes += [f"The evidence supports option {t} as much as the correct answer, so {t} may also be correct. "
                      f"Rewrite {t} so it is clearly wrong." for t in targets]
        elif code == "length_cue":
            notes.append(f"The correct answer {key} is noticeably longer than the wrong options. Make all four "
                         f"options similar in length.")
        elif code == "stem_too_simple":
            notes.append("The question is too short or simple. Rewrite it as a complete question of 15 to 35 words.")
        elif code == "stem_too_dense":
            notes.append("The question is too long or complex. Rewrite it with simpler sentence structure.")
    return notes


def repair_messages(context: str, items: Sequence[dict], flag_lists: Sequence[Sequence[str]]) -> list[dict]:
    blocks = []
    for n, (item, flags) in enumerate(zip(items, flag_lists), 1):
        shown = {k: item[k] for k in ("question", "options", "answer", "evidence") if k in item}
        problems = "\n".join(f"  - {note}" for note in repair_instructions(item, flags))
        blocks.append(f"Question {n}:\n{json.dumps(shown, ensure_ascii=False, indent=2)}\nProblems:\n{problems}")
    prompt = REPAIR_PROMPT.format(CONTEXT=context, ITEMS="\n\n".join(blocks))
    return [{"role": "system", "content": SYSTEM_V2}, {"role": "user", "content": prompt}]
