"""Content quality validator for Jevyam Technologies LinkedIn posts.

Evaluates generated captions against B2B agency writing standards, service alignment,
anti-AI-cliche rules, and factual safety before saving or generating creatives.
"""

import re
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from agent.pillars import OFFICIAL_SERVICE_PILLARS, get_pillar_by_name


BANNED_AI_PHRASES: List[str] = [
    "in today's fast-paced digital world",
    "in today's fast paced digital world",
    "in today's competitive landscape",
    "in today's digital landscape",
    "at jevyam technologies, we believe",
    "the future of business is",
    "revolutionize your business",
    "unlock the power of",
    "take your business to the next level",
    "game changer",
    "game-changer",
    "mind-blowing",
    "10x your business",
    "architectural longevity",
    "conversion velocity",
    "synergistic",
    "delve into",
]

GENERIC_TOPICS: List[str] = [
    "the future of ai",
    "technology is changing the world",
    "why digital transformation matters",
    "ai is revolutionizing businesses",
]

# Detect unsupported performance percentages/multipliers like "340%", "10x revenue"
_FAKE_STAT_PATTERN = re.compile(
    r"\b(\d{2,3}%\s+(?:increase|boost|growth|faster|more|higher|reduction|roi|revenue)|"
    r"(?:boost|increase|grow|save|cut|reduce)\w*(?:\s+\w+){0,3}\s+(?:by\s+)?\d{2,3}%|"
    r"[2-9]\d?x\s+(?:faster|more|roi|revenue|growth|leads))",
    re.IGNORECASE,
)

# Detect emoji characters to prevent emoji walls
_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]",
    flags=re.UNICODE,
)


class QualityValidationResult(BaseModel):
    """Result of deterministic + heuristic content quality evaluation."""

    passed: bool = Field(..., description="Whether the post passes all quality gates")
    issues: List[str] = Field(default_factory=list, description="Specific quality failures found")
    score: int = Field(default=100, description="Quality score from 0 to 100")


def validate_post_quality(
    topic: str,
    hook: str,
    caption: str,
    hashtags: List[str],
    call_to_action: str,
    service_category: Optional[str] = None,
) -> QualityValidationResult:
    """Validate generated post content against agency quality standards.

    Checks:
    1. Relates to one of Jevyam's 8 official services.
    2. Topic is specific rather than generic fluff.
    3. Caption avoids banned AI-cliche phrases and corporate jargon.
    4. Company name ('Jevyam') is not forced into every paragraph.
    5. No unsupported fake statistics or exaggerated claims.
    6. Paragraphs are readable (not walls of text) and emojis are restrained.
    7. Hashtags count is within 3 to 6 (prefer 3-5) and CTA is present.
    """
    issues: List[str] = []
    score = 100
    full_text = f"{hook}\n{caption}".strip()
    lower_text = full_text.lower()
    lower_topic = (topic or "").strip().lower()

    # 1. Service alignment check
    matched_pillar = get_pillar_by_name(service_category) if service_category else None
    if not matched_pillar:
        issues.append(f"Service category '{service_category}' does not match any of the 8 official Jevyam services.")
        score -= 25

    # 2. Generic topic check
    for gen in GENERIC_TOPICS:
        if gen in lower_topic and len(lower_topic) < 65:
            issues.append(f"Topic '{topic}' is too generic ('{gen}'). Tie it to a concrete business problem.")
            score -= 25
            break

    # 3. Banned AI phrases
    for phrase in BANNED_AI_PHRASES:
        if phrase in lower_text:
            issues.append(f"Caption contains banned AI-cliche or jargon phrase: '{phrase}'.")
            score -= 20

    # 4. Over-mention of company name
    jevyam_mentions = len(re.findall(r"\bje+vyam\b", lower_text))
    if jevyam_mentions > 2:
        issues.append(f"Company name 'Jevyam' appears {jevyam_mentions} times; keep mentions natural (max 1-2).")
        score -= 15

    # 5. Unsupported stats / claims check
    stat_match = _FAKE_STAT_PATTERN.search(full_text)
    if stat_match:
        issues.append(f"Caption appears to contain an unsupported performance statistic: '{stat_match.group(0)}'.")
        score -= 25

    # 6. Readability: paragraph length & emoji restraint
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", caption or "") if p.strip()]
    long_paras = [p for p in paragraphs if len(p) > 420]
    if long_paras:
        issues.append(f"Found {len(long_paras)} overly long paragraph(s) (>420 chars); break them up for mobile readability.")
        score -= 10

    emojis_found = _EMOJI_PATTERN.findall(caption or "")
    if len(emojis_found) > 5:
        issues.append(f"Too many emojis ({len(emojis_found)}); keep emojis minimal (0-3 max).")
        score -= 10

    # 7. CTA & Hashtags check
    if not call_to_action or len(call_to_action.strip()) < 10:
        issues.append("Call to action is missing or too short.")
        score -= 15

    if not hashtags or len(hashtags) < 3 or len(hashtags) > 6:
        issues.append(f"Expected 3 to 5 hashtags (got {len(hashtags) if hashtags else 0}).")
        score -= 10

    if len(caption or "") < 120:
        issues.append("Caption is too short (<120 chars) to provide practical insight.")
        score -= 20

    return QualityValidationResult(
        passed=(len(issues) == 0),
        issues=issues,
        score=max(0, score),
    )
