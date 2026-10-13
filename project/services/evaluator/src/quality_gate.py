from typing import List, Tuple
from .schemas import MCQItem

def audit_quality_gate(item: MCQItem, semantic_alignment: float) -> Tuple[bool, List[str]]:
    """
    Applies rule-based pedagogical sanity checks on the generated MCQ item.
    Returns: (passed: bool, flags: List[str])
    """
    flags: List[str] = []

    options = [item.option_a.strip(), item.option_b.strip(), item.option_c.strip(), item.option_d.strip()]

    # 1. Check for empty fields
    if not item.question_stem.strip():
        flags.append("EMPTY_STEM: Question stem is blank.")
    if any(len(opt) == 0 for opt in options):
        flags.append("EMPTY_OPTION: One or more options are blank.")

    # 2. Check for duplicate options (case-insensitive)
    lower_opts = [opt.lower() for opt in options]
    if len(set(lower_opts)) < len(options):
        flags.append("DUPLICATE_OPTIONS: Two or more answer choices are identical.")

    # 3. Check for length asymmetry (The "Longest Answer is Correct" bias)
    correct_text = item.get_correct_text().strip()
    distractors = item.get_distractors()
    avg_distractor_len = sum(len(d.split()) for d in distractors) / max(1, len(distractors))
    correct_len = len(correct_text.split())

    if avg_distractor_len > 0 and correct_len >= 3.0 * avg_distractor_len and correct_len > 15:
        flags.append("LENGTH_BIAS: Correct answer is substantially longer than foils (>3x).")

    # 4. Check semantic alignment threshold
    if semantic_alignment < 0.08:
        flags.append("LOW_ALIGNMENT: Question stem shares virtually no semantic vocabulary with source text.")

    # 5. Check stem word count
    stem_words = item.question_stem.strip().split()
    if len(stem_words) < 5:
        flags.append("TRIVIAL_STEM: Question stem is too brief (< 5 words) for technical assessment.")

    passed = len(flags) == 0
    return passed, flags
