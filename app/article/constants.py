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
