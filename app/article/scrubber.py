"""Post-processing scrubber to clean AI-generated article content."""

import re
from dataclasses import dataclass

from app.article.constants import (
    AI_FILLER_OPENERS,
    AI_WORDS_RE,
    SENTENCE_END_RE,
    ZERO_WIDTH_RE,
)
from app.article.models import ArticleContent, ArticleSection, FaqItem

_FILLER_RE = re.compile(
    r"(?:^|\.\s+)(" + "|".join(AI_FILLER_OPENERS) + ")",
    re.IGNORECASE | re.MULTILINE,
)

# Max sentences per paragraph
_MAX_SENTENCES_PER_PARA = 6


@dataclass
class ScrubStats:
    """Tracks what the scrubber changed and found."""
    filler_removed: int = 0
    paragraphs_split: int = 0
    zero_width_stripped: int = 0
    em_dashes_found: int = 0
    ai_words_found: int = 0


def _scrub_text(text: str, stats: ScrubStats) -> str:
    """Apply safe scrubbing operations to a text block."""
    # 1. Strip zero-width Unicode
    new_text = ZERO_WIDTH_RE.sub("", text)
    stats.zero_width_stripped += len(text) - len(new_text)
    text = new_text

    # 2. Count em-dashes and double-hyphens (logged, not scrubbed)
    stats.em_dashes_found += text.count("\u2014") + text.count(" -- ")

    # 3. Count AI-favored words (logged, not replaced)
    stats.ai_words_found += len(AI_WORDS_RE.findall(text))

    # 4. Remove AI filler opener phrases
    def _remove_filler(match: re.Match) -> str:
        stats.filler_removed += 1
        if match.group(0).startswith("."):
            return ". "
        return ""

    text = _FILLER_RE.sub(_remove_filler, text)

    # 5. Split long paragraphs
    paragraphs = text.split("\n\n")
    result_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sentences = SENTENCE_END_RE.split(para)
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
