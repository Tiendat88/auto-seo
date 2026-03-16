"""Post-processing scrubber to clean AI-generated article content."""

import re
from dataclasses import dataclass

from app.article.models import ArticleContent, ArticleSection, FaqItem

# Zero-width Unicode characters to strip
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")

# AI filler opener phrases to remove (case-insensitive, at sentence/paragraph start)
_FILLER_OPENERS = [
    r"In today's digital landscape,?\s*",
    r"In today's fast-paced world,?\s*",
    r"It's worth noting that\s+",
    r"It's important to note that\s+",
    r"When it comes to\s+",
]
_FILLER_RE = re.compile(
    r"(?:^|\.\s+)(" + "|".join(_FILLER_OPENERS) + ")",
    re.IGNORECASE | re.MULTILINE,
)

# Word substitutions: AI-favored → natural
_WORD_SUBS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bleverage\b", re.IGNORECASE), "use"),
    (re.compile(r"\butilize\b", re.IGNORECASE), "use"),
    (re.compile(r"\butilization\b", re.IGNORECASE), "use"),
    (re.compile(r"\bdelve\b", re.IGNORECASE), "explore"),
    (re.compile(r"\bdelving\b", re.IGNORECASE), "exploring"),
    (re.compile(r"\btapestry\b", re.IGNORECASE), "mix"),
    (re.compile(r"\bnavigate\b(?!\s+to\b)", re.IGNORECASE), "handle"),
    (re.compile(r"\blandscape\b", re.IGNORECASE), "space"),
    (re.compile(r"\bparadigm\b", re.IGNORECASE), "approach"),
    (re.compile(r"\bsynergy\b", re.IGNORECASE), "collaboration"),
    (re.compile(r"\bholistic\b", re.IGNORECASE), "complete"),
    (re.compile(r"\brobust\b", re.IGNORECASE), "strong"),
]

# Sentence boundary regex (approximate)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Max sentences per paragraph
_MAX_SENTENCES_PER_PARA = 6


@dataclass
class ScrubStats:
    """Tracks what the scrubber changed."""
    filler_removed: int = 0
    words_substituted: int = 0
    paragraphs_split: int = 0
    zero_width_stripped: int = 0
    em_dashes_replaced: int = 0


def _scrub_text(text: str, stats: ScrubStats) -> str:
    """Apply all scrubbing operations to a text block."""
    # 1. Strip zero-width Unicode
    new_text = _ZERO_WIDTH.sub("", text)
    stats.zero_width_stripped += len(text) - len(new_text)
    text = new_text

    # 2. Replace em-dashes with --
    count = text.count("\u2014")
    stats.em_dashes_replaced += count
    text = text.replace("\u2014", " -- ")

    # 3. Remove AI filler opener phrases
    def _remove_filler(match: re.Match) -> str:
        stats.filler_removed += 1
        full = match.group(0)
        if full.startswith("."):
            return ". "
        return ""

    text = _FILLER_RE.sub(_remove_filler, text)

    # 4. Word substitutions
    for pattern, replacement in _WORD_SUBS:
        new_text = pattern.sub(replacement, text)
        if new_text != text:
            stats.words_substituted += len(pattern.findall(text))
            text = new_text

    # 5. Split long paragraphs
    paragraphs = text.split("\n\n")
    result_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sentences = _SENTENCE_END.split(para)
        if len(sentences) > _MAX_SENTENCES_PER_PARA:
            stats.paragraphs_split += 1
            chunks = []
            for i in range(0, len(sentences), _MAX_SENTENCES_PER_PARA):
                chunk = " ".join(sentences[i:i + _MAX_SENTENCES_PER_PARA])
                chunks.append(chunk)
            result_paragraphs.append("\n\n".join(chunks))
        else:
            result_paragraphs.append(para)

    text = "\n\n".join(result_paragraphs)

    # 6. Clean up artifacts
    text = re.sub(r"  +", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = text.strip()

    return text


def scrub_article(article: ArticleContent) -> tuple[ArticleContent, ScrubStats]:
    """Apply content scrubbing to all sections and FAQ answers."""
    stats = ScrubStats()
    sections = [
        ArticleSection(
            heading=s.heading,
            heading_level=s.heading_level,
            content=_scrub_text(s.content, stats),
        )
        for s in article.sections
    ]
    faq = [
        FaqItem(
            question=f.question,
            answer=_scrub_text(f.answer, stats),
        )
        for f in article.faq
    ]
    return ArticleContent(sections=sections, faq=faq), stats
