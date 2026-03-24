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
_FENCE_RE = re.compile(r"^\s*([`~]{3,})")
_ORDERED_LIST_MARKER_RE = re.compile(r"(?<!\S)\d+\.\s+")
_ORDERED_LIST_SPLIT_RE = re.compile(r"(?<=\S)\s+(?=\d+\.\s+)")
_BOLD_BULLET_MARKER_RE = re.compile(r"(?<!\S)(?:[-*])\s+\*\*[^:\n]{1,80}:\*\*\s+")
_BOLD_BULLET_SPLIT_RE = re.compile(
    r"(?<=\S)\s+(?=(?:[-*]\s+\*\*[^:\n]{1,80}:\*\*\s+))"
)
_LIST_LINE_RE = re.compile(r"^\s*(?:[-*]\s+|\d+\.\s+)")
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")

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
    ordered_lists_normalized: int = 0
    bullet_runs_normalized: int = 0
    code_fences_closed: int = 0


def _toggle_fence_state(
    line: str,
    in_fence: bool,
    fence_char: str,
    fence_len: int,
) -> tuple[bool, str, int]:
    match = _FENCE_RE.match(line)
    if not match:
        return in_fence, fence_char, fence_len

    marker = match.group(1)
    char = marker[0]
    length = len(marker)
    if not in_fence:
        return True, char, length
    if char == fence_char and length >= fence_len:
        return False, "", 0
    return in_fence, fence_char, fence_len


def _normalize_collapsed_lists(text: str, stats: ScrubStats) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for line in lines:
        if not in_fence:
            ordered_matches = list(_ORDERED_LIST_MARKER_RE.finditer(line))
            if len(ordered_matches) >= 2 and not line[:ordered_matches[0].start()].strip():
                normalized = _ORDERED_LIST_SPLIT_RE.sub("\n", line)
                if normalized != line:
                    stats.ordered_lists_normalized += 1
                    line = normalized

            bullet_matches = list(_BOLD_BULLET_MARKER_RE.finditer(line))
            if len(bullet_matches) >= 2 and not line[:bullet_matches[0].start()].strip():
                normalized = _BOLD_BULLET_SPLIT_RE.sub("\n", line)
                if normalized != line:
                    stats.bullet_runs_normalized += 1
                    line = normalized

        out.append(line)
        in_fence, fence_char, fence_len = _toggle_fence_state(
            line, in_fence, fence_char, fence_len
        )

    return "\n".join(out)


def _close_unmatched_code_fence(text: str, stats: ScrubStats) -> str:
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in text.splitlines():
        in_fence, fence_char, fence_len = _toggle_fence_state(
            line, in_fence, fence_char, fence_len
        )

    if not in_fence:
        return text

    stats.code_fences_closed += 1
    closing = fence_char * max(fence_len, 3)
    return text.rstrip() + f"\n{closing}"


def _contains_code_fence(text: str) -> bool:
    return any(_FENCE_RE.match(line) for line in text.splitlines())


def _split_long_paragraphs(text: str, stats: ScrubStats) -> str:
    if _contains_code_fence(text):
        return text

    paragraphs = text.split("\n\n")
    result_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if (
            _LIST_LINE_RE.match(para)
            or _TABLE_LINE_RE.match(para)
            or ("\n" in para and any(
                _LIST_LINE_RE.match(line) or _TABLE_LINE_RE.match(line)
                for line in para.splitlines()
            ))
        ):
            result_paragraphs.append(para)
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

    return "\n\n".join(result_paragraphs)


def _cleanup_spacing(text: str) -> str:
    cleaned_lines: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for line in text.splitlines():
        if in_fence or _FENCE_RE.match(line):
            cleaned_lines.append(line.rstrip())
        else:
            compact = re.sub(r"  +", " ", line).rstrip()
            cleaned_lines.append(compact)
        in_fence, fence_char, fence_len = _toggle_fence_state(
            line, in_fence, fence_char, fence_len
        )

    return "\n".join(cleaned_lines).strip()


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

    # 5. Repair structural markdown without changing article claims
    text = _normalize_collapsed_lists(text, stats)
    text = _close_unmatched_code_fence(text, stats)

    # 6. Split long prose paragraphs outside fenced/code-like blocks
    text = _split_long_paragraphs(text, stats)

    # 7. Clean up non-code spacing artifacts
    text = _cleanup_spacing(text)

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
