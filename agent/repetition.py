"""Repetition and duplicate content detection."""

from difflib import SequenceMatcher
import re
from typing import Any, List, Optional, Tuple


def normalize_text(text: str) -> str:
    """Normalize text by lowercasing, stripping punctuation, and collapsing whitespace."""
    if not text:
        return ""
    # Remove non-alphanumeric except spaces
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    # Collapse multiple whitespaces
    return " ".join(cleaned.split())


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate normalized sequence similarity between two texts (0.0 to 1.0)."""
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0
    return SequenceMatcher(None, norm1, norm2).ratio()


def calculate_token_overlap(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity over word tokens."""
    tokens1 = set(normalize_text(text1).split())
    tokens2 = set(normalize_text(text2).split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def check_repetition(
    candidate_topic: str,
    candidate_hook: Optional[str] = None,
    candidate_caption: Optional[str] = None,
    previous_posts: Optional[List[Any]] = None,
    topic_threshold: float = 0.70,
    hook_threshold: float = 0.75,
) -> Tuple[bool, Optional[str]]:
    """Check if candidate content repeats or is too similar to any previous post.

    Args:
        candidate_topic: Proposed topic.
        candidate_hook: Proposed hook.
        candidate_caption: Proposed caption text.
        previous_posts: List of previous post dictionaries or models.
        topic_threshold: Similarity ratio above which a topic is flagged.
        hook_threshold: Similarity ratio above which a hook is flagged.

    Returns:
        Tuple of (is_repetition: bool, reason: Optional[str]).
    """
    if not previous_posts:
        return False, None

    norm_cand_topic = normalize_text(candidate_topic)

    for item in previous_posts:
        prev_id = "unknown"
        prev_topic = ""
        prev_hook = ""
        prev_caption = ""

        if isinstance(item, dict):
            prev_id = item.get("post_id", "previous_post")
            prev_topic = item.get("topic", "")
            prev_hook = item.get("hook", "")
            prev_caption = item.get("caption", "")
        elif hasattr(item, "topic"):
            prev_id = getattr(item, "post_id", "previous_post")
            prev_topic = getattr(item, "topic", "")
            prev_hook = getattr(item, "hook", "")
            prev_caption = getattr(item, "caption", "")

        # 1. Exact or near-exact topic check
        norm_prev_topic = normalize_text(prev_topic)
        if norm_cand_topic and norm_prev_topic:
            if norm_cand_topic == norm_prev_topic:
                return True, f"Identical topic to post {prev_id}: '{prev_topic}'"

            sim = calculate_similarity(candidate_topic, prev_topic)
            if sim >= topic_threshold:
                return (
                    True,
                    f"Topic is too similar to post {prev_id} (similarity {sim:.2f}): '{prev_topic}'",
                )

            # High token overlap check
            overlap = calculate_token_overlap(candidate_topic, prev_topic)
            if overlap >= 0.80:
                return (
                    True,
                    f"Topic shares {overlap*100:.0f}% word overlap with post {prev_id}: '{prev_topic}'",
                )

        # 2. Hook check
        if candidate_hook and prev_hook:
            norm_cand_hook = normalize_text(candidate_hook)
            norm_prev_hook = normalize_text(prev_hook)
            if norm_cand_hook == norm_prev_hook:
                return True, f"Identical hook to post {prev_id}: '{prev_hook}'"

            hook_sim = calculate_similarity(candidate_hook, prev_hook)
            if hook_sim >= hook_threshold:
                return (
                    True,
                    f"Hook is too similar to post {prev_id} (similarity {hook_sim:.2f})",
                )

        # 3. Caption structural repetition (check first 2 lines)
        if candidate_caption and prev_caption:
            cand_first_lines = " ".join(candidate_caption.strip().splitlines()[:2])
            prev_first_lines = " ".join(prev_caption.strip().splitlines()[:2])
            lead_sim = calculate_similarity(cand_first_lines, prev_first_lines)
            if lead_sim >= 0.85:
                return (
                    True,
                    f"Post opening structure repeats post {prev_id}",
                )

    return False, None
