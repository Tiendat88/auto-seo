"""Tests validating SEO constraints on article output."""

from app.article.models import (
    HeadingLevel,
)


class TestSeoConstraints:
    """Validate that generated article output meets SEO requirements."""

    def test_primary_keyword_in_title(self, sample_seo_metadata, sample_analysis):
        kw = sample_analysis.keywords.primary.lower()
        assert kw in sample_seo_metadata.title_tag.lower()

    def test_primary_keyword_in_intro(self, sample_article, sample_analysis):
        kw = sample_analysis.keywords.primary.lower()
        intro = sample_article.sections[0].content.lower()
        assert kw in intro

    def test_title_tag_length(self, sample_seo_metadata):
        assert len(sample_seo_metadata.title_tag) <= 60

    def test_meta_description_length(self, sample_seo_metadata):
        assert len(sample_seo_metadata.meta_description) <= 160

    def test_heading_hierarchy_valid(self, sample_article):
        """H1 exists, no skipped levels."""
        levels = [s.heading_level for s in sample_article.sections]
        assert HeadingLevel.H1 in levels
        assert levels.count(HeadingLevel.H1) == 1

        level_map = {"h1": 1, "h2": 2, "h3": 3}
        for i in range(1, len(levels)):
            curr = level_map[levels[i]]
            prev = level_map[levels[i - 1]]
            assert curr <= prev + 1, f"Heading skip at index {i}: {levels[i-1]} → {levels[i]}"

    def test_minimum_h2_sections(self, sample_article):
        h2_count = sum(1 for s in sample_article.sections if s.heading_level == HeadingLevel.H2)
        assert h2_count >= 3

    def test_faq_section_present(self, sample_article):
        assert len(sample_article.faq) >= 3

    def test_internal_links_count(self, sample_links):
        assert 3 <= len(sample_links.internal) <= 5

    def test_external_references_count(self, sample_links):
        assert 2 <= len(sample_links.external) <= 4

    def test_keyword_density_range(self, sample_keyword_analysis):
        density = sample_keyword_analysis.primary.density
        assert 0.5 <= density <= 5.0, f"Keyword density {density}% outside acceptable range"

    def test_keyword_in_multiple_locations(self, sample_keyword_analysis):
        locations = sample_keyword_analysis.primary.locations
        assert len(locations) >= 2, "Primary keyword should appear in at least 2 locations"

    def test_slug_format(self, sample_seo_metadata):
        slug = sample_seo_metadata.slug
        assert slug == slug.lower()
        assert " " not in slug
        assert all(c.isalnum() or c == "-" for c in slug)
