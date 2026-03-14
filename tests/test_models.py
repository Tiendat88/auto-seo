"""Tests for Pydantic model validation and serialization."""

import pytest
from pydantic import ValidationError

from app.article.models import (
    ArticleBrief,
    ArticleContent,
    ArticleOutline,
    ArticleSection,
    BrandVoice,
    CompetitiveAnalysis,
    HeadingLevel,
    KeywordAnalysis,
    KeywordCluster,
    KeywordDistribution,
    KeywordUsage,
    OutlineHeading,
    QualityScore,
    ReviewIssue,
    ReviewResult,
    ReviewSeverity,
    SectionKeywordDensity,
    SeoMetadata,
    SeoMetaOptions,
)
from app.article.schema import SchemaMarkup, SnippetOpportunity
from app.job.models import ArticleRequest, JobStatus
from app.serp.models import SerpData, SerpResult


class TestSerpModels:
    def test_serp_result_extracts_domain(self):
        r = SerpResult(rank=1, url="https://www.example.com/path", title="Test", snippet="Snip")
        assert r.domain == "www.example.com"

    def test_serp_result_rank_bounds(self):
        with pytest.raises(ValidationError):
            SerpResult(rank=0, url="https://x.com", title="T", snippet="S")

    def test_serp_data_requires_results(self):
        with pytest.raises(ValidationError):
            SerpData(query="test", results=[])

    def test_serp_data_round_trip(self, sample_serp_data: SerpData):
        json_str = sample_serp_data.model_dump_json()
        restored = SerpData.model_validate_json(json_str)
        assert len(restored.results) == 10
        assert restored.query == sample_serp_data.query


class TestArticleModels:
    def test_section_computes_word_count(self):
        section = ArticleSection(
            heading="Test", heading_level=HeadingLevel.H2, content="one two three four five"
        )
        assert section.word_count == 5

    def test_article_content_computes_total(self):
        article = ArticleContent(
            sections=[
                ArticleSection(heading="A", heading_level=HeadingLevel.H1, content="word " * 100),
                ArticleSection(heading="B", heading_level=HeadingLevel.H2, content="word " * 200),
            ]
        )
        assert article.total_word_count == 300

    def test_seo_metadata_title_max_length(self):
        with pytest.raises(ValidationError):
            SeoMetadata(
                title_tag="x" * 61,
                meta_description="desc",
                primary_keyword="kw",
                slug="slug",
            )

    def test_seo_metadata_valid(self):
        meta = SeoMetadata(
            title_tag="Best Tools for Remote Teams",
            meta_description="Discover top productivity tools for remote teams.",
            primary_keyword="productivity tools",
            slug="best-tools-remote-teams",
        )
        assert meta.slug == "best-tools-remote-teams"

    def test_quality_score_bounds(self):
        with pytest.raises(ValidationError):
            QualityScore(
                overall=1.5,
                dimensions=[],
                passes_threshold=True,
            )

    def test_outline_min_headings(self):
        with pytest.raises(ValidationError):
            ArticleOutline(
                h1="Test",
                headings=[
                    OutlineHeading(level=HeadingLevel.H2, text="A", target_word_count=100),
                ],
                estimated_total_words=100,
            )


class TestCompetitiveAnalysis:
    def test_round_trip(self, sample_analysis: CompetitiveAnalysis):
        json_str = sample_analysis.model_dump_json()
        restored = CompetitiveAnalysis.model_validate_json(json_str)
        assert restored.keywords.primary == "productivity tools"
        assert len(restored.themes) == 3

    def test_requires_at_least_one_theme(self):
        with pytest.raises(ValidationError):
            CompetitiveAnalysis(
                keywords=KeywordCluster(primary="test"),
                themes=[],
                avg_word_count=1000,
                search_intent="informational",
            )


class TestReviewModels:
    def test_review_result_passing(self):
        review = ReviewResult(
            passed=True,
            summary="Article is well-written.",
            strengths=["Good structure", "Clear examples"],
            issues=[],
        )
        assert review.passed is True
        assert review.revision_instructions is None

    def test_review_result_failing_with_issues(self):
        review = ReviewResult(
            passed=False,
            summary="Needs improvement.",
            issues=[
                ReviewIssue(
                    category="engagement_quality",
                    severity=ReviewSeverity.CRITICAL,
                    description="No concrete examples",
                    suggestion="Add 2-3 real-world examples",
                ),
            ],
            revision_instructions="[engagement_quality] No concrete examples -> Add examples",
        )
        assert review.passed is False
        assert len(review.issues) == 1
        assert review.revision_instructions is not None

    def test_review_severity_values(self):
        assert ReviewSeverity.CRITICAL == "critical"
        assert ReviewSeverity.MAJOR == "major"
        assert ReviewSeverity.MINOR == "minor"

    def test_review_issue_optional_section(self):
        issue = ReviewIssue(
            category="tone",
            severity=ReviewSeverity.MINOR,
            description="Slightly inconsistent",
            suggestion="Maintain formal tone",
        )
        assert issue.affected_section is None

    def test_review_result_round_trip(self):
        review = ReviewResult(
            passed=False,
            summary="Needs work.",
            issues=[
                ReviewIssue(
                    category="factual_consistency",
                    severity=ReviewSeverity.MAJOR,
                    description="Contradictory claims",
                    affected_section="Section 2",
                    suggestion="Reconcile paragraphs 1 and 3",
                ),
            ],
            strengths=["Good SEO coverage"],
        )
        json_str = review.model_dump_json()
        restored = ReviewResult.model_validate_json(json_str)
        assert restored.issues[0].severity == ReviewSeverity.MAJOR
        assert restored.issues[0].affected_section == "Section 2"


class TestRequestModels:
    def test_article_request_defaults(self):
        req = ArticleRequest(topic="test topic")
        assert req.target_word_count == 1500
        assert req.language == "en"

    def test_article_request_topic_min_length(self):
        with pytest.raises(ValidationError):
            ArticleRequest(topic="ab")

    def test_article_request_word_count_bounds(self):
        with pytest.raises(ValidationError):
            ArticleRequest(topic="valid topic", target_word_count=100)

    def test_article_request_language_pattern(self):
        with pytest.raises(ValidationError):
            ArticleRequest(topic="valid topic", language="eng")

    def test_job_status_values(self):
        assert JobStatus.PENDING == "pending"
        assert JobStatus.EDITING == "editing"
        assert JobStatus.COMPLETED == "completed"


class TestNegativeCases:
    def test_slug_rejects_spaces(self):
        with pytest.raises(ValidationError):
            SeoMetadata(
                title_tag="Valid Title Here",
                meta_description="Valid description here.",
                primary_keyword="kw",
                slug="invalid slug",
            )

    def test_slug_rejects_uppercase(self):
        with pytest.raises(ValidationError):
            SeoMetadata(
                title_tag="Valid Title Here",
                meta_description="Valid description here.",
                primary_keyword="kw",
                slug="Invalid-Slug",
            )

    def test_slug_accepts_valid(self):
        meta = SeoMetadata(
            title_tag="Valid Title Here",
            meta_description="Valid description here.",
            primary_keyword="kw",
            slug="valid-slug-123",
        )
        assert meta.slug == "valid-slug-123"

    def test_external_ref_rejects_javascript_url(self):
        from app.article.models import ExternalReference
        with pytest.raises(ValidationError):
            ExternalReference(
                title="Bad",
                url="javascript:alert(1)",
                authority_reason="none",
                placement_section="intro",
            )

    def test_external_ref_accepts_https(self):
        from app.article.models import ExternalReference
        ref = ExternalReference(
            title="Good",
            url="https://example.com",
            authority_reason="reputable",
            placement_section="intro",
        )
        assert ref.url == "https://example.com"

    def test_serp_provider_unknown_raises(self):
        from app.errors import SerpError
        from app.serp.client import get_serp_provider
        with pytest.raises(SerpError, match="Unknown SERP provider"):
            get_serp_provider(provider="typo")

    def test_article_word_count_includes_faq(self):
        from app.article.models import ArticleContent, ArticleSection, FaqItem
        article = ArticleContent(
            sections=[
                ArticleSection(heading="A", heading_level="h1", content="word " * 100),
            ],
            faq=[FaqItem(question="What is this?", answer="This is a test answer with words.")],
        )
        # Should be > 100 because FAQ words are included
        assert article.total_word_count > 100


class TestArticleBrief:
    def test_valid_brief(self):
        brief = ArticleBrief(
            target_audience="Remote team leads",
            tone="Authoritative",
            angle="Integration-first perspective",
            differentiators=["Real cost analysis"],
            content_gaps_to_fill=["AI-powered productivity"],
        )
        assert brief.target_audience == "Remote team leads"
        assert brief.angle == "Integration-first perspective"

    def test_brief_defaults(self):
        brief = ArticleBrief(
            target_audience="Developers",
            tone="Technical",
            angle="Practical",
        )
        assert brief.differentiators == []
        assert brief.content_gaps_to_fill == []

    def test_brief_round_trip(self):
        brief = ArticleBrief(
            target_audience="Test",
            tone="Casual",
            angle="Unique angle",
            differentiators=["d1", "d2"],
            content_gaps_to_fill=["g1"],
        )
        json_str = brief.model_dump_json()
        restored = ArticleBrief.model_validate_json(json_str)
        assert restored == brief


class TestArticleOutlineWithBrief:
    def test_outline_with_brief(self, sample_outline: ArticleOutline):
        assert sample_outline.brief is not None
        assert sample_outline.brief.target_audience

    def test_outline_without_brief(self):
        outline = ArticleOutline(
            h1="Test",
            headings=[
                OutlineHeading(level=HeadingLevel.H2, text="A", target_word_count=100),
                OutlineHeading(level=HeadingLevel.H2, text="B", target_word_count=100),
                OutlineHeading(level=HeadingLevel.H2, text="C", target_word_count=100),
            ],
            estimated_total_words=300,
        )
        assert outline.brief is None

    def test_outline_brief_round_trip(self, sample_outline: ArticleOutline):
        json_str = sample_outline.model_dump_json()
        restored = ArticleOutline.model_validate_json(json_str)
        assert restored.brief is not None
        assert restored.brief.target_audience == sample_outline.brief.target_audience


class TestBrandVoice:
    def test_valid_brand_voice(self):
        bv = BrandVoice(
            brand_name="Acme Corp",
            voice_description="Professional but friendly",
            writing_examples=["Example text 1", "Example text 2"],
            style_notes="Use active voice. Avoid jargon.",
        )
        assert bv.brand_name == "Acme Corp"
        assert len(bv.writing_examples) == 2

    def test_all_fields_optional(self):
        bv = BrandVoice()
        assert bv.brand_name is None
        assert bv.writing_examples == []

    def test_max_writing_examples(self):
        with pytest.raises(ValidationError):
            BrandVoice(writing_examples=["a", "b", "c", "d"])

    def test_round_trip(self):
        bv = BrandVoice(brand_name="Test", voice_description="Casual")
        restored = BrandVoice.model_validate_json(bv.model_dump_json())
        assert restored.brand_name == "Test"


class TestSeoMetaOptions:
    def test_valid_meta_options(self):
        opts = SeoMetaOptions(
            title_options=[f"Title {i}" for i in range(5)],
            description_options=[f"Desc {i}" for i in range(5)],
        )
        assert len(opts.title_options) == 5
        assert len(opts.description_options) == 5

    def test_too_few_options_rejected(self):
        with pytest.raises(ValidationError):
            SeoMetaOptions(
                title_options=["Only one"],
                description_options=[f"Desc {i}" for i in range(5)],
            )

    def test_too_many_options_rejected(self):
        with pytest.raises(ValidationError):
            SeoMetaOptions(
                title_options=[f"Title {i}" for i in range(6)],
                description_options=[f"Desc {i}" for i in range(5)],
            )


class TestKeywordDistributionModel:
    def test_valid_distribution(self):
        dist = KeywordDistribution(
            primary_by_section=[
                SectionKeywordDensity(
                    section_heading="Intro", keyword="test",
                    count=3, density=1.5, word_count=200,
                ),
            ],
            distribution_score=0.85,
        )
        assert dist.distribution_score == 0.85

    def test_distribution_in_keyword_analysis(self):
        kw = KeywordAnalysis(
            primary=KeywordUsage(keyword="test", count=5, density=1.0, locations=[]),
            keyword_distribution=KeywordDistribution(
                primary_by_section=[
                    SectionKeywordDensity(
                        section_heading="Intro", keyword="test",
                        count=5, density=2.5, word_count=200,
                    ),
                ],
                distribution_score=0.9,
            ),
        )
        assert kw.keyword_distribution is not None
        assert kw.keyword_distribution.distribution_score == 0.9

    def test_distribution_optional(self):
        kw = KeywordAnalysis(
            primary=KeywordUsage(keyword="test", count=5, density=1.0, locations=[]),
        )
        assert kw.keyword_distribution is None


class TestSchemaModels:
    def test_schema_markup_with_faq(self):
        markup = SchemaMarkup(
            article_schema={"@type": "Article", "headline": "Test"},
            faq_schema={"@type": "FAQPage", "mainEntity": []},
        )
        assert markup.faq_schema is not None

    def test_schema_markup_without_faq(self):
        markup = SchemaMarkup(
            article_schema={"@type": "Article", "headline": "Test"},
        )
        assert markup.faq_schema is None

    def test_snippet_opportunity(self):
        opp = SnippetOpportunity(
            type="list",
            section_heading="Steps",
            description="Has numbered items",
            current_format_ok=False,
            suggestion="Use markdown list",
        )
        assert opp.type == "list"
        assert not opp.current_format_ok
