"""Deterministic brand name detection via regex pattern matching.

Complements LLM-based analysis with fast, reliable text matching.
Generates name variations (camelCase, hyphenated, abbreviated, etc.),
builds word-boundary regex patterns, and scores matches by confidence.
"""

import re
from dataclasses import dataclass, field

_CORPORATE_SUFFIXES = (
    "Inc", "LLC", "Ltd", "Corp", "Corporation", "Company", "Co",
    "Group", "Holdings", "Enterprises", "Technologies", "Solutions",
    "Systems", "Services", "International", "Global", "Worldwide",
)

_NEGATIVE_PATTERNS = (
    r"avoid\b", r"don't use\b", r"do not use\b", r"worse than\b",
    r"inferior to\b", r"scam\b", r"overpriced\b", r"not recommended\b",
    r"stay away from\b", r"poor quality\b",
)

_NEGATIVE_WINDOW = 60  # chars before match to scan for negative context


@dataclass(frozen=True)
class DetectionConfig:
    """Configuration for brand detection behavior."""

    case_sensitive: bool = False
    whole_word: bool = True
    confidence_threshold: float = 0.3
    ignored_suffixes: tuple[str, ...] = _CORPORATE_SUFFIXES
    negative_patterns: tuple[str, ...] = _NEGATIVE_PATTERNS
    negative_window: int = _NEGATIVE_WINDOW
    aliases: dict[str, list[str]] = field(default_factory=dict)


DEFAULT_CONFIG = DetectionConfig()


@dataclass(frozen=True)
class BrandMatch:
    """A single brand mention found in text."""

    text: str
    start: int
    end: int
    confidence: float
    variation_type: str
    negative_context: bool


# ---------------------------------------------------------------------------
# Name variation generation
# ---------------------------------------------------------------------------


def _strip_suffixes(name: str, suffixes: tuple[str, ...]) -> str:
    """Remove trailing corporate suffixes."""
    for suffix in suffixes:
        patterns = [f", {suffix}", f" {suffix}"]
        for pat in patterns:
            if name.endswith(pat):
                return name[: -len(pat)].rstrip()
            if name.endswith(f"{pat}."):
                return name[: -len(f"{pat}.")].rstrip()
    return name


def generate_name_variations(
    brand_name: str,
    config: DetectionConfig = DEFAULT_CONFIG,
) -> list[tuple[str, str]]:
    """Generate brand name variations for matching.

    Returns list of (variation_text, variation_type) pairs.
    """
    name = _strip_suffixes(brand_name.strip(), config.ignored_suffixes)
    if not name:
        return []

    variations: list[tuple[str, str]] = [(name, "exact")]
    words = name.split()

    if len(words) > 1:
        # No spaces
        joined = "".join(words)
        variations.append((joined, "no_space"))

        # Hyphenated
        variations.append(("-".join(words), "hyphenated"))

        # camelCase (only if distinct from no_space)
        camel = words[0].lower() + "".join(w.capitalize() for w in words[1:])
        if camel.lower() != joined.lower():
            variations.append((camel, "camel_case"))

        # PascalCase (only if distinct from no_space)
        pascal = "".join(w.capitalize() for w in words)
        if pascal.lower() != joined.lower() and pascal != name:
            variations.append((pascal, "pascal_case"))

    # Symbol substitutions
    if "&" in name:
        variations.append((name.replace("&", "and"), "ampersand_expanded"))
        variations.append((name.replace(" & ", "And"), "ampersand_camel"))
    if "+" in name:
        variations.append((name.replace("+", "plus"), "plus_expanded"))

    # Domain-style (.com, .io)
    base = words[0] if words else name
    if "." not in base:
        for tld in (".com", ".io"):
            variations.append((base.lower() + tld, "domain"))

    # Aliases from config
    key = brand_name.lower()
    for alias in config.aliases.get(key, []):
        variations.append((alias, "alias"))

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for text, vtype in variations:
        lower = text.lower()
        if lower not in seen:
            seen.add(lower)
            unique.append((text, vtype))

    return unique


# ---------------------------------------------------------------------------
# Pattern building
# ---------------------------------------------------------------------------

# Confidence scores per variation type
_VARIATION_CONFIDENCE: dict[str, float] = {
    "exact": 1.0,
    "alias": 0.95,
    "no_space": 0.85,
    "pascal_case": 0.8,
    "camel_case": 0.8,
    "hyphenated": 0.75,
    "ampersand_expanded": 0.7,
    "ampersand_camel": 0.7,
    "plus_expanded": 0.7,
    "domain": 0.6,
}


def _build_pattern(
    text: str, *, whole_word: bool, case_sensitive: bool,
) -> re.Pattern[str]:
    """Build a regex pattern for a single variation."""
    escaped = re.escape(text)

    # Allow possessive forms (brand's) and plural (brands)
    if whole_word:
        pattern = rf"\b{escaped}(?:'s|s)?\b"
    else:
        pattern = escaped

    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def build_detection_patterns(
    brand_name: str, config: DetectionConfig = DEFAULT_CONFIG,
) -> list[tuple[re.Pattern[str], str, float]]:
    """Build regex patterns from brand name + variations.

    Returns list of (compiled_pattern, variation_type, confidence) tuples.
    """
    variations = generate_name_variations(brand_name, config)
    patterns: list[tuple[re.Pattern[str], str, float]] = []

    for text, vtype in variations:
        if len(text) < 2:
            continue
        pattern = _build_pattern(
            text,
            whole_word=config.whole_word,
            case_sensitive=config.case_sensitive,
        )
        confidence = _VARIATION_CONFIDENCE.get(vtype, 0.5)
        patterns.append((pattern, vtype, confidence))

    return patterns


# ---------------------------------------------------------------------------
# Negative context detection
# ---------------------------------------------------------------------------


def _compile_negative_patterns(
    patterns: tuple[str, ...],
) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_NEGATIVE_RE_CACHE: dict[tuple[str, ...], list[re.Pattern[str]]] = {}


def _get_negative_patterns(patterns: tuple[str, ...]) -> list[re.Pattern[str]]:
    if patterns not in _NEGATIVE_RE_CACHE:
        _NEGATIVE_RE_CACHE[patterns] = _compile_negative_patterns(patterns)
    return _NEGATIVE_RE_CACHE[patterns]


def _has_negative_context(
    text: str, match_start: int, config: DetectionConfig,
) -> bool:
    """Check if the text window before the match contains negative signals."""
    window_start = max(0, match_start - config.negative_window)
    window = text[window_start:match_start].lower()

    for neg_re in _get_negative_patterns(config.negative_patterns):
        if neg_re.search(window):
            return True
    return False


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_brand_mentions(
    text: str,
    brand_name: str,
    config: DetectionConfig = DEFAULT_CONFIG,
) -> list[BrandMatch]:
    """Find all brand mentions in text with confidence scoring.

    Returns matches sorted by position, deduplicated by span overlap.
    Matches below ``config.confidence_threshold`` are excluded.
    """
    if not text or not brand_name:
        return []

    patterns = build_detection_patterns(brand_name, config)
    raw_matches: list[BrandMatch] = []

    for pattern, vtype, confidence in patterns:
        for m in pattern.finditer(text):
            if confidence < config.confidence_threshold:
                continue
            negative = _has_negative_context(text, m.start(), config)
            raw_matches.append(BrandMatch(
                text=m.group(),
                start=m.start(),
                end=m.end(),
                confidence=confidence,
                variation_type=vtype,
                negative_context=negative,
            ))

    # Deduplicate overlapping spans — keep highest confidence
    raw_matches.sort(key=lambda m: (m.start, -m.confidence))
    deduped: list[BrandMatch] = []
    last_end = -1
    for match in raw_matches:
        if match.start >= last_end:
            deduped.append(match)
            last_end = match.end

    return deduped


def detect_brands_batch(
    text: str,
    brand_names: list[str],
    config: DetectionConfig = DEFAULT_CONFIG,
) -> dict[str, list[BrandMatch]]:
    """Detect multiple brands in one text. Returns {brand_name: [matches]}."""
    return {
        name: detect_brand_mentions(text, name, config)
        for name in brand_names
    }
