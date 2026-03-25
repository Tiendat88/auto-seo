"""Shared constants for article processing (scorer, scrubber, prompts)."""

import re

ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\ufeff]")

# Regex patterns — used by scrubber for removal at sentence/paragraph start
AI_FILLER_OPENERS = [
    r"In today's digital landscape,?\s*",
    r"In today's fast-paced world,?\s*",
    r"It's worth noting that\s+",
    r"It's important to note that\s+",
    r"When it comes to\s+",
]

# Literal strings for scorer detection. `.+` entries are intentional regex.
AI_FILLER_PHRASES = frozenset({
    "in today's digital landscape",
    "in today's fast-paced world",
    "it's worth noting that",
    "it's important to note that",
    "when it comes to",
    "in the realm of",
    "at the end of the day",
    "in conclusion",
    "without further ado",
    "it goes without saying",
    "needless to say",
    "as we all know",
    "in this day and age",
    "dive deep into",
    "game-changer",
    r"take your .+ to the next level",
    "unlock the power",
    "harness the potential",
    "embark on a journey",
    "navigating the complexities",
})

AI_WORDS_RE = re.compile(
    r"\b(?:leverage|utilize|delve|tapestry|paradigm|synergy|holistic|robust)\b",
    re.IGNORECASE,
)

VAGUE_WORDS = frozenset({
    "things", "stuff", "very", "really", "quite",
    "basically", "actually", "essentially", "generally", "overall",
})

SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

# Markdown fence / list structure patterns — shared by pipeline + scrubber
FENCE_RE = re.compile(r"^\s*([`~]{3,})")
ORDERED_LIST_MARKER_RE = re.compile(r"(?<!\S)\d+\.\s+")
BOLD_BULLET_MARKER_RE = re.compile(r"(?<!\S)(?:[-*])\s+\*\*[^:\n]{1,80}:\*\*\s+")


def toggle_fence_state(
    line: str,
    in_fence: bool,
    fence_char: str,
    fence_len: int,
) -> tuple[bool, str, int]:
    """Track fenced code block state across lines."""
    match = FENCE_RE.match(line)
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
