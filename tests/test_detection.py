"""Tests for brand detection — name variations, pattern matching, negative context."""


from app.brand.detection import (
    DetectionConfig,
    detect_brand_mentions,
    detect_brands_batch,
    generate_name_variations,
)

# ---------------------------------------------------------------------------
# Name variation generation
# ---------------------------------------------------------------------------


class TestGenerateNameVariations:
    def test_single_word_brand(self) -> None:
        variations = generate_name_variations("Notion")
        types = {v[1] for v in variations}
        assert "exact" in types
        assert "domain" in types
        names = {v[0] for v in variations}
        assert "Notion" in names
        assert "notion.com" in names

    def test_multi_word_brand(self) -> None:
        variations = generate_name_variations("Visual Studio")
        types = {v[1] for v in variations}
        assert "exact" in types
        assert "no_space" in types
        assert "hyphenated" in types
        # camelCase "visualStudio" dedupes with no_space "VisualStudio" (same lowered)
        names = {v[0].lower() for v in variations}
        assert "visual studio" in names
        assert "visualstudio" in names
        assert "visual-studio" in names

    def test_camel_case_dedupes_with_no_space(self) -> None:
        """camelCase is deduped when it matches no_space (case-insensitive)."""
        # For 2-word brands, camelCase and no_space are often the same lowered
        variations = generate_name_variations("Open AI")
        # "openAi" and "OpenAI" both lowercase to "openai" → deduplicated
        lowered = [v[0].lower() for v in variations]
        assert len(lowered) == len(set(lowered))

    def test_ampersand_expansion(self) -> None:
        variations = generate_name_variations("Ben & Jerry")
        names = {v[0] for v in variations}
        assert "Ben and Jerry" in names

    def test_plus_expansion(self) -> None:
        variations = generate_name_variations("Disney+")
        names = {v[0] for v in variations}
        assert "Disneyplus" in names

    def test_corporate_suffix_stripped(self) -> None:
        variations = generate_name_variations("Notion Inc")
        names = {v[0] for v in variations}
        assert "Notion" in names
        assert "Notion Inc" not in names

    def test_aliases_included(self) -> None:
        config = DetectionConfig(aliases={"notion": ["Notion.so", "NotionHQ"]})
        variations = generate_name_variations("Notion", config)
        names = {v[0] for v in variations}
        assert "Notion.so" in names
        assert "NotionHQ" in names

    def test_empty_name(self) -> None:
        assert generate_name_variations("") == []

    def test_deduplication(self) -> None:
        variations = generate_name_variations("AI")
        names = [v[0].lower() for v in variations]
        assert len(names) == len(set(names))

    def test_domain_variations(self) -> None:
        variations = generate_name_variations("Slack")
        names = {v[0] for v in variations}
        assert "slack.com" in names
        assert "slack.io" in names


# ---------------------------------------------------------------------------
# Mention detection
# ---------------------------------------------------------------------------


class TestDetectBrandMentions:
    def test_exact_match(self) -> None:
        text = "I recommend using Notion for team collaboration."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) >= 1
        assert matches[0].text == "Notion"
        assert matches[0].confidence == 1.0
        assert matches[0].variation_type == "exact"
        assert not matches[0].negative_context

    def test_case_insensitive_default(self) -> None:
        text = "Try notion for your notes."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 1
        assert matches[0].text == "notion"

    def test_case_sensitive_config(self) -> None:
        config = DetectionConfig(case_sensitive=True)
        text = "Try notion for your notes."
        matches = detect_brand_mentions(text, "Notion", config)
        assert len(matches) == 0

    def test_possessive_form(self) -> None:
        text = "Notion's collaboration features are excellent."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 1
        assert "Notion" in matches[0].text

    def test_plural_form(self) -> None:
        text = "Both Notions and Evernotes have their strengths."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 1

    def test_no_match(self) -> None:
        text = "I use Evernote for everything."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 0

    def test_multiple_occurrences(self) -> None:
        text = "Notion is great. I love Notion. Notion beats everything."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 3

    def test_negative_context_detected(self) -> None:
        text = "You should avoid Notion because it's too complex."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 1
        assert matches[0].negative_context is True

    def test_negative_context_scam(self) -> None:
        text = "Many consider it a scam. Notion has poor reviews."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 1
        assert matches[0].negative_context is True

    def test_no_negative_context_when_distant(self) -> None:
        text = "Avoid complexity. " + "x" * 100 + " Notion is great."
        matches = detect_brand_mentions(text, "Notion")
        assert len(matches) == 1
        assert matches[0].negative_context is False

    def test_multi_word_brand(self) -> None:
        text = "Visual Studio Code is a great editor. Try VisualStudio too."
        matches = detect_brand_mentions(text, "Visual Studio")
        assert len(matches) >= 1

    def test_empty_text(self) -> None:
        assert detect_brand_mentions("", "Notion") == []

    def test_empty_brand(self) -> None:
        assert detect_brand_mentions("Some text", "") == []

    def test_confidence_threshold(self) -> None:
        config = DetectionConfig(confidence_threshold=0.9)
        text = "Check out notion.com for more info."
        matches = detect_brand_mentions(text, "Notion", config)
        # Domain match has 0.6 confidence, should be filtered
        domain_matches = [m for m in matches if m.variation_type == "domain"]
        assert len(domain_matches) == 0

    def test_overlapping_spans_deduplicated(self) -> None:
        text = "Notion is the best."
        matches = detect_brand_mentions(text, "Notion")
        starts = [m.start for m in matches]
        assert len(starts) == len(set(starts))


# ---------------------------------------------------------------------------
# Batch detection
# ---------------------------------------------------------------------------


class TestDetectBrandsBatch:
    def test_multiple_brands(self) -> None:
        text = "Notion vs Obsidian vs Evernote — which is best?"
        result = detect_brands_batch(text, ["Notion", "Obsidian", "Evernote"])
        assert len(result["Notion"]) >= 1
        assert len(result["Obsidian"]) >= 1
        assert len(result["Evernote"]) >= 1

    def test_missing_brand(self) -> None:
        text = "Notion is great for notes."
        result = detect_brands_batch(text, ["Notion", "Todoist"])
        assert len(result["Notion"]) >= 1
        assert len(result["Todoist"]) == 0

    def test_empty_brand_list(self) -> None:
        result = detect_brands_batch("Some text", [])
        assert result == {}


# ---------------------------------------------------------------------------
# Config overrides
# ---------------------------------------------------------------------------


class TestDetectionConfig:
    def test_custom_negative_patterns(self) -> None:
        config = DetectionConfig(negative_patterns=("terrible",))
        text = "It's terrible. Notion should fix this."
        matches = detect_brand_mentions(text, "Notion", config)
        assert len(matches) == 1
        assert matches[0].negative_context is True

    def test_whole_word_disabled(self) -> None:
        config = DetectionConfig(whole_word=False)
        text = "The Notional value is high."
        matches = detect_brand_mentions(text, "Notion", config)
        assert len(matches) >= 1

    def test_whole_word_enabled_filters_partial(self) -> None:
        text = "The Notional value is high."
        matches = detect_brand_mentions(text, "Notion")
        # With whole_word=True (default), "Notional" should not match "Notion"
        exact_matches = [m for m in matches if m.variation_type == "exact"]
        assert len(exact_matches) == 0
