import re
import math
from typing import List, Set, Tuple
from collections import Counter
import textstat

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", 
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", 
    "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", 
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", 
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", 
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", 
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", 
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", 
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", 
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", 
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves"
}

def _tokenize(text: str, filter_stopwords: bool = True) -> List[str]:
    """Extracts alphanumeric lowercase tokens, filtering standard stopwords."""
    tokens = re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower())
    if filter_stopwords:
        return [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens

def _tokenize_set(text: str) -> Set[str]:
    """Extracts unique lowercase tokens, filtering standard stopwords."""
    return set(_tokenize(text, filter_stopwords=True))

# --- Pillar 1: Semantic Alignment (TF Cosine Similarity) ---
def calculate_semantic_alignment(source_text: str, question_stem: str) -> float:
    """
    Computes Content-Word Term Frequency Cosine Similarity between source text and question stem.
    Filtering grammatical stopwords ensures only domain vocabulary is evaluated.
    """
    if not source_text or not question_stem:
        return 0.0

    tokens_src = _tokenize(source_text, filter_stopwords=True)
    tokens_stem = _tokenize(question_stem, filter_stopwords=True)

    if not tokens_src or not tokens_stem:
        return 0.0

    vec_src = Counter(tokens_src)
    vec_stem = Counter(tokens_stem)

    intersection = set(vec_src.keys()) & set(vec_stem.keys())
    numerator = sum(vec_src[token] * vec_stem[token] for token in intersection)

    sum_src = sum(count ** 2 for count in vec_src.values())
    sum_stem = sum(count ** 2 for count in vec_stem.values())
    denominator = math.sqrt(sum_src) * math.sqrt(sum_stem)

    if denominator == 0.0:
        return 0.0

    score = float(numerator / denominator)
    return round(max(0.0, min(1.0, score)), 4)

# --- Pillar 2: Linguistic Complexity (Flesch-Kincaid Grade Level) ---
def calculate_linguistic_complexity(text: str) -> Tuple[float, float]:
    """
    Calculates Flesch-Kincaid Grade Level and Reading Ease score.
    Returns: (grade_level, reading_ease)
    """
    cleaned = text.strip()
    if not cleaned or len(_tokenize(cleaned)) < 3:
        return 0.0, 100.0

    try:
        grade = float(textstat.flesch_kincaid_grade(cleaned))
        ease = float(textstat.flesch_reading_ease(cleaned))
        return round(grade, 2), round(ease, 2)
    except Exception:
        return 0.0, 100.0

# --- Pillar 3: Distractor Plausibility & Diversity (Jaccard) ---
def _jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    if not set1 and not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return float(intersection / union) if union > 0 else 0.0

def calculate_distractor_plausibility(correct_answer: str, distractors: List[str]) -> float:
    """
    Measures the average token Jaccard similarity between the correct answer and incorrect foils.
    Higher plausibility indicates that distractors share domain terminology and avoid trivial giveaways.
    """
    if not distractors or not correct_answer:
        return 0.0

    correct_set = _tokenize_set(correct_answer)
    if not correct_set:
        return 0.0

    scores = [_jaccard_similarity(correct_set, _tokenize_set(foil)) for foil in distractors]
    avg_score = sum(scores) / len(scores)
    return round(float(avg_score), 4)

def calculate_distractor_diversity(distractors: List[str]) -> float:
    """
    Measures pairwise divergence among distractors (1.0 - pairwise Jaccard).
    Ensures foils test distinct technical misconceptions rather than being minor rewordings.
    """
    if len(distractors) < 2:
        return 1.0

    sets = [_tokenize_set(f) for f in distractors]
    divergences = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            sim = _jaccard_similarity(sets[i], sets[j])
            divergences.append(1.0 - sim)

    avg_div = sum(divergences) / len(divergences) if divergences else 1.0
    return round(float(avg_div), 4)
