"""AEO content scoring checks: direct answer, heading hierarchy, readability."""

from typing import TYPE_CHECKING

import textstat
from pydantic import BaseModel, Field

from app.aeo.models import CheckResult
from app.aeo.parser import ParsedContent
from app.article.constants import SENTENCE_END_RE

if TYPE_CHECKING:
    from app.llm import LlmClient

HEDGE_PHRASES = [
    "it depends", "may vary", "in some cases",
    "this varies", "generally speaking",
]


# --- LLM schema for direct answer analysis ---


class DirectAnswerAnalysis(BaseModel):
    """LLM assessment of whether a paragraph provides a direct answer."""

    is_declarative: bool = Field(
        ...,
        description=(
            "True if the paragraph contains at least one clear declarative statement "
            "with a subject and verb that directly answers an implied question."
        ),
    )
    reasoning: str = Field(
        ...,
        description="One-sentence explanation of the assessment.",
    )


_DIRECT_ANSWER_PROMPT = """\
Analyze this opening paragraph and determine if it provides a direct, \
declarative answer. A declarative statement has a clear subject and verb \
and states a fact or answer (not a question, not vague hedging).

Paragraph:
---
{paragraph}
---

Respond with JSON matching the schema. Be strict: generic introductions \
like "In today's world..." or "Many people wonder..." are NOT declarative answers."""


# --- Check A: Direct Answer Detection ---


async def check_direct_answer(content: ParsedContent, llm: "LlmClient") -> CheckResult:
    """Score first paragraph for directness, brevity, and confidence."""
    para = content.first_paragraph
    word_count = len(para.split()) if para else 0

    # LLM-based declarative detection
    is_declarative = False
    if para and word_count >= 3:
        try:
            result = await llm.generate_structured(
                _DIRECT_ANSWER_PROMPT.format(paragraph=para),
                DirectAnswerAnalysis,
                max_tokens=256,
                use_cache=True,
            )
            is_declarative = result.is_declarative
        except Exception:
            # Fallback: assume declarative if paragraph is short and doesn't start with a question
            is_declarative = not para.strip().endswith("?")

    # Hedge detection
    para_lower = para.lower()
    has_hedge = any(h in para_lower for h in HEDGE_PHRASES)

    # Scoring
    if word_count > 90:
        score = 0
        rec = (
            f"Opening paragraph is {word_count} words. "
            "Rewrite it as a direct answer in under 60 words."
        )
    elif word_count > 60:
        score = 8
        rec = (
            f"Opening paragraph is {word_count} words. "
            "Trim to under 60 words with a direct, declarative answer."
        )
    elif not is_declarative or has_hedge:
        score = 12
        parts = []
        if has_hedge:
            parts.append("Remove hedge phrases for a more confident answer")
        if not is_declarative:
            parts.append("Use a clear declarative statement with subject and verb")
        rec = ". ".join(parts) + "."
    else:
        score = 20
        rec = None

    return CheckResult(
        check_id="direct_answer",
        name="Direct Answer Detection",
        passed=score == 20,
        score=score,
        details={
            "word_count": word_count,
            "threshold": 60,
            "is_declarative": is_declarative,
            "has_hedge_phrase": has_hedge,
        },
        recommendation=rec,
    )


# --- Check B: H-tag Hierarchy ---


def check_htag_hierarchy(content: ParsedContent) -> CheckResult:
    """Validate heading structure: single H1, no skipped levels, proper order."""
    headings = content.headings
    h_tags_found = [tag for tag, _ in headings]
    violations: list[str] = []

    # Count H1s
    h1_count = sum(1 for tag in h_tags_found if tag == "h1")
    if h1_count == 0:
        violations.append("Missing H1 tag")
    elif h1_count > 1:
        violations.append(f"Multiple H1 tags found ({h1_count})")

    # No heading before H1
    if headings and headings[0][0] != "h1" and h1_count > 0:
        violations.append(f"Heading {headings[0][0].upper()} appears before H1")

    # No skipped levels
    for i in range(1, len(headings)):
        prev_level = int(headings[i - 1][0][1])
        curr_level = int(headings[i][0][1])
        if curr_level > prev_level + 1:
            violations.append(
                f"Skipped heading level: {headings[i - 1][0].upper()} → {headings[i][0].upper()}"
            )

    # Scoring
    missing_h1 = h1_count == 0
    if missing_h1 or len(violations) >= 3:
        score = 0
    elif len(violations) <= 2 and len(violations) > 0:
        score = 12
    else:
        score = 20

    rec = None
    if violations:
        rec = "Fix heading hierarchy: " + "; ".join(violations) + "."

    return CheckResult(
        check_id="htag_hierarchy",
        name="H-tag Hierarchy",
        passed=score == 20,
        score=score,
        details={
            "violations": violations,
            "h_tags_found": h_tags_found,
        },
        recommendation=rec,
    )


# --- Check C: Snippet Readability ---


def check_readability(content: ParsedContent) -> CheckResult:
    """Score Flesch-Kincaid grade level and identify complex sentences."""
    text = content.text
    if not text or len(text.split()) < 10:
        return CheckResult(
            check_id="readability",
            name="Snippet Readability",
            passed=False,
            score=0,
            details={
                "fk_grade_level": 0.0,
                "target_range": "7-9",
                "complex_sentences": [],
            },
            recommendation="Insufficient text to compute readability.",
        )

    fk_grade = round(textstat.flesch_kincaid_grade(text), 1)

    # Find 3 most complex sentences by syllable/word ratio
    sentences = [s.strip() for s in SENTENCE_END_RE.split(text) if s.strip()]
    ranked: list[tuple[float, str]] = []
    for sent in sentences:
        wc = len(sent.split())
        if wc < 3:
            continue
        complexity = textstat.syllable_count(sent) / wc
        ranked.append((complexity, sent))
    ranked.sort(reverse=True)
    complex_sentences = [s for _, s in ranked[:3]]

    # Scoring
    grade_rounded = round(fk_grade)
    if 7 <= grade_rounded <= 9:
        score = 20
    elif grade_rounded in (6, 10):
        score = 14
    elif grade_rounded in (5, 11):
        score = 8
    else:
        score = 0

    rec = None
    if score < 20:
        direction = "Simplify" if fk_grade > 9 else "Add depth to"
        rec = (
            f"Content reads at Grade {fk_grade}. "
            f"{direction} sentences to reach Grade 7-9."
        )

    return CheckResult(
        check_id="readability",
        name="Snippet Readability",
        passed=score == 20,
        score=score,
        details={
            "fk_grade_level": fk_grade,
            "target_range": "7-9",
            "complex_sentences": complex_sentences,
        },
        recommendation=rec,
    )


# --- Score Aggregation ---


def compute_aeo_score(checks: list[CheckResult]) -> tuple[int, str]:
    """Aggregate check scores into an overall AEO readiness score and band."""
    raw = sum(c.score for c in checks)
    max_possible = sum(c.max_score for c in checks)
    score = round(raw / max_possible * 100) if max_possible else 0
    if score >= 85:
        band = "AEO Optimized"
    elif score >= 65:
        band = "Needs Improvement"
    elif score >= 40:
        band = "Significant Gaps"
    else:
        band = "Not AEO Ready"
    return score, band
