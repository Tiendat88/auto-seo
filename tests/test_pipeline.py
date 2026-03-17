"""Tests for the pipeline runner — state transitions, resume, edit loop, helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.article.models import (
    ArticleBrief,
    ArticleOutline,
    CompetitiveAnalysis,
    CompetitorTheme,
    ExternalReference,
    HeadingLevel,
    InternalLink,
    KeywordCluster,
    LinkSuggestions,
    OutlineHeading,
    ReviewIssue,
    ReviewResult,
    ReviewSeverity,
    ScoreDimension,
    SeoMetadata,
    SeoMetaOptions,
)
from app.article.pipeline import (
    _determine_resume_index,
    _merge_reviews,
    _merge_score_dimensions,
    _parse_article_markdown,
    _ScorePair,
    run_pipeline,
)
from app.job.models import Job, JobStatus
from app.serp.models import SerpData, SerpResult

# --- Factories ---


ARTICLE_MARKDOWN = (
    "# Test Article\n\n"
    "Intro content about test keyword and productivity tools for remote teams.\n\n"
    "## Section 1\n\n"
    "Section content with test keyword repeated. " * 15 + "\n\n"
    "## Section 2\n\n"
    "More content about test topics and collaboration. " * 15 + "\n\n"
    "## FAQ\n\n"
    "### What is test?\n\n"
    "Test answer here."
)


def _apply_test_settings(mock_settings: MagicMock) -> None:
    """Apply common test settings to mock pipeline settings."""
    mock_settings.firecrawl_api_key = ""
    mock_settings.content_fetch_top_n = 0
    mock_settings.persist_events = False


def _make_outline() -> ArticleOutline:
    return ArticleOutline(
        h1="Test Article",
        brief=ArticleBrief(
            target_audience="Developers",
            tone="Professional",
            angle="Practical guide",
            differentiators=["Unique approach"],
            content_gaps_to_fill=["Missing details"],
        ),
        headings=[
            OutlineHeading(
                level=HeadingLevel.H1, text="Test Article", target_word_count=100,
                key_points=["intro"], keywords_to_include=["test"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2, text="Section 1", target_word_count=200,
                key_points=["point1"], keywords_to_include=["test"],
            ),
            OutlineHeading(
                level=HeadingLevel.H2, text="Section 2", target_word_count=200,
                key_points=["point2"], keywords_to_include=["test"],
            ),
        ],
        estimated_total_words=500,
        faq_questions=["What is test?"],
    )


def _make_seo_meta() -> SeoMetadata:
    return SeoMetadata(
        title_tag="Test Article Title",
        meta_description="A test meta description for the article.",
        primary_keyword="test",
        slug="test-article",
    )


def _make_links() -> LinkSuggestions:
    return LinkSuggestions(
        internal=[
            InternalLink(
                anchor_text=f"link{i}",
                suggested_target_topic=f"Topic{i}",
                placement_context=f"ctx{i}",
            )
            for i in range(3)
        ],
        external=[
            ExternalReference(
                title=f"Ref{i}",
                url=f"https://ref{i}.com",
                authority_reason="good",
                placement_section="intro",
            )
            for i in range(2)
        ],
    )


def _make_analysis() -> CompetitiveAnalysis:
    return CompetitiveAnalysis(
        keywords=KeywordCluster(primary="test", secondary=["a", "b"]),
        themes=[CompetitorTheme(theme="Theme1", frequency=5, subtopics=["sub1"])],
        avg_word_count=1500,
        search_intent="informational",
    )


def _make_serp_data() -> SerpData:
    return SerpData(
        query="test",
        results=[
            SerpResult(
                rank=i + 1,
                url=f"https://example{i}.com",
                title=f"Result {i}",
                snippet=f"Snippet {i}",
            )
            for i in range(10)
        ],
    )


def _make_score_pair() -> _ScorePair:
    return _ScorePair(dimensions=[
        ScoreDimension(name="content_depth", score=0.9, feedback="good"),
        ScoreDimension(name="differentiation", score=0.8, feedback="ok"),
    ])


def _make_passing_review() -> ReviewResult:
    return ReviewResult(
        passed=True,
        summary="Good article.",
        strengths=["Well-structured"],
        issues=[],
    )


def _make_failing_review() -> ReviewResult:
    return ReviewResult(
        passed=False,
        summary="Article needs improvements.",
        issues=[
            ReviewIssue(
                category="engagement_quality",
                severity=ReviewSeverity.MAJOR,
                description="Lacks concrete examples",
                suggestion="Add real-world case studies",
            ),
        ],
        revision_instructions="[engagement_quality] Lacks concrete examples -> Add case studies",
    )


def _make_meta_options() -> SeoMetaOptions:
    return SeoMetaOptions(
        title_options=[f"Title Option {i}" for i in range(5)],
        description_options=[f"Description option {i}" for i in range(5)],
    )


def _smart_generate_structured(model_map: dict):
    """Return a mock that dispatches based on the schema type."""
    async def _mock(prompt, schema, **kwargs):
        if schema in model_map:
            return model_map[schema]
        raise ValueError(f"Unexpected schema: {schema}")
    return _mock


# --- TestResumeIndex ---


class TestResumeIndex:
    async def test_empty_job_starts_at_zero(self, sample_job):
        assert _determine_resume_index(sample_job) == 0

    async def test_job_with_serp_starts_at_one(self, sample_job, sample_serp_data):
        sample_job.set_serp(sample_serp_data)
        assert _determine_resume_index(sample_job) == 1

    async def test_job_with_all_data_returns_length(
        self, sample_job, sample_serp_data, sample_analysis, sample_outline,
        sample_article, sample_seo_metadata, sample_keyword_analysis, sample_links,
    ):
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        sample_job.set_outline(sample_outline)
        sample_job.set_article(sample_article)
        sample_job.set_seo_metadata(sample_seo_metadata)
        sample_job.set_keyword_analysis(sample_keyword_analysis)
        sample_job.set_links(sample_links)
        # Quality data still missing -> scoring step (index 3)
        assert _determine_resume_index(sample_job) == 3


# --- TestPipelineExecution ---


class TestPipelineExecution:
    async def test_pipeline_completes_with_mocks(self, session, sample_job):
        """Pipeline should run all steps and set status to COMPLETED."""
        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_serp = AsyncMock()

        mock_serp.search = AsyncMock(return_value=_make_serp_data())
        mock_llm.generate_text = AsyncMock(return_value=ARTICLE_MARKDOWN)
        mock_llm.generate_structured = AsyncMock(side_effect=_smart_generate_structured({
            CompetitiveAnalysis: _make_analysis(),
            ArticleOutline: _make_outline(),
            SeoMetadata: _make_seo_meta(),
            LinkSuggestions: _make_links(),
            SeoMetaOptions: _make_meta_options(),
            _ScorePair: _make_score_pair(),
            ReviewResult: _make_passing_review(),
        }))

        with (
            patch("app.article.pipeline.settings") as mock_settings,
            patch("app.article.pipeline.get_llm_council", return_value=[mock_llm]),
        ):
            mock_settings.quality_threshold = 0.3
            mock_settings.max_revisions = 2
            _apply_test_settings(mock_settings)
            await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.COMPLETED
        assert refreshed.serp_data is not None
        assert refreshed.analysis_data is not None
        assert refreshed.outline_data is not None
        assert refreshed.article_data is not None
        assert refreshed.quality_data is not None
        assert refreshed.review_data is not None

    async def test_pipeline_handles_step_failure(self, session, sample_job):
        """Pipeline should set FAILED status on exception."""
        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_serp = AsyncMock()
        mock_serp.search = AsyncMock(side_effect=Exception("SERP API down"))

        await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.FAILED
        assert "SERP API down" in refreshed.error

    async def test_pipeline_resumes_from_last_step(
        self, session, sample_job, sample_serp_data, sample_analysis,
    ):
        """Pipeline should skip already-completed steps on resume."""
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        session.add(sample_job)
        await session.commit()

        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_serp = AsyncMock()

        mock_llm.generate_text = AsyncMock(return_value=ARTICLE_MARKDOWN)
        mock_llm.generate_structured = AsyncMock(side_effect=_smart_generate_structured({
            ArticleOutline: _make_outline(),
            SeoMetadata: _make_seo_meta(),
            LinkSuggestions: _make_links(),
            SeoMetaOptions: _make_meta_options(),
            _ScorePair: _make_score_pair(),
            ReviewResult: _make_passing_review(),
        }))

        with (
            patch("app.article.pipeline.settings") as mock_settings,
            patch("app.article.pipeline.get_llm_council", return_value=[mock_llm]),
        ):
            mock_settings.quality_threshold = 0.3
            mock_settings.max_revisions = 2
            _apply_test_settings(mock_settings)
            await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        mock_serp.search.assert_not_called()
        assert refreshed.status == JobStatus.COMPLETED

    async def test_nonexistent_job_does_nothing(self, session):
        """Pipeline should log error for missing job."""
        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_serp = AsyncMock()

        await run_pipeline("nonexistent-id", session, mock_llm, mock_serp)
        mock_serp.search.assert_not_called()


# --- TestMarkdownParser ---


class TestMarkdownParser:
    def test_normal_headings(self):
        outline = _make_outline()
        md = (
            "# Test Article\n\nIntro text.\n\n"
            "## Section 1\n\nBody one.\n\n"
            "## Section 2\n\nBody two."
        )
        sections, faq = _parse_article_markdown(md, outline)

        assert len(sections) == 3
        assert sections[0].heading == "Test Article"
        assert sections[0].heading_level == HeadingLevel.H1
        assert sections[1].heading == "Section 1"
        assert sections[1].heading_level == HeadingLevel.H2
        assert sections[2].heading == "Section 2"
        assert sections[2].heading_level == HeadingLevel.H2
        assert faq == []

    def test_fuzzy_matched_headings(self):
        """Headings that are substrings of outline headings should match level."""
        outline = ArticleOutline(
            h1="Guide",
            brief=None,
            headings=[
                OutlineHeading(
                    level=HeadingLevel.H1, text="Guide", target_word_count=100,
                    key_points=[], keywords_to_include=[],
                ),
                OutlineHeading(
                    level=HeadingLevel.H2, text="Getting Started with Tools",
                    target_word_count=200, key_points=[], keywords_to_include=[],
                ),
                OutlineHeading(
                    level=HeadingLevel.H3, text="Advanced Configuration",
                    target_word_count=200, key_points=[], keywords_to_include=[],
                ),
            ],
            estimated_total_words=500,
        )
        md = (
            "# Guide\n\nIntro.\n\n"
            "## Getting Started\n\nSome content.\n\n"
            "### Advanced Configuration Tips\n\nDetailed content."
        )
        sections, _ = _parse_article_markdown(md, outline)

        assert len(sections) == 3
        # "Getting Started" is substring of "Getting Started with Tools" -> H2
        assert sections[1].heading_level == HeadingLevel.H2
        # "Advanced Configuration Tips" contains "Advanced Configuration" -> H3
        assert sections[2].heading_level == HeadingLevel.H3

    def test_faq_parsing(self):
        outline = _make_outline()
        md = (
            "# Test Article\n\nIntro.\n\n"
            "## Section 1\n\nContent.\n\n"
            "## FAQ\n\n"
            "### What is test?\n\nTest answer.\n\n"
            "### Why test?\n\nBecause reasons."
        )
        sections, faq = _parse_article_markdown(md, outline)

        assert len(sections) == 2
        assert sections[0].heading == "Test Article"
        assert sections[1].heading == "Section 1"
        assert len(faq) == 2
        assert faq[0].question == "What is test?"
        assert faq[0].answer == "Test answer."
        assert faq[1].question == "Why test?"
        assert faq[1].answer == "Because reasons."

    def test_no_headings_fallback(self):
        outline = _make_outline()
        md = "Just plain text without any headings."
        sections, faq = _parse_article_markdown(md, outline)

        assert len(sections) == 1
        assert sections[0].heading == "Article"
        assert sections[0].heading_level == HeadingLevel.H2
        assert sections[0].content == md
        assert faq == []

    def test_infers_level_from_hash_count(self):
        outline = _make_outline()
        md = (
            "# Test Article\n\nIntro.\n\n"
            "## Completely New Heading\n\nBody.\n\n"
            "### Sub Detail\n\nDetail."
        )
        sections, _ = _parse_article_markdown(md, outline)

        assert sections[1].heading_level == HeadingLevel.H2  # ## → H2
        assert sections[2].heading_level == HeadingLevel.H3  # ### → H3

    def test_frequently_asked_variant(self):
        outline = _make_outline()
        md = (
            "# Test Article\n\nContent.\n\n"
            "## Frequently Asked Questions\n\n"
            "### How?\n\nLike this.\n\n"
            "### Why?\n\nBecause."
        )
        sections, faq = _parse_article_markdown(md, outline)

        assert len(sections) == 1
        assert len(faq) == 2


# --- TestEditLoop ---


class TestEditLoop:
    async def test_edit_loop_triggers_on_failing_quality(
        self, session, sample_job,
    ):
        """Edit loop: fail quality -> edit -> re-score (pass) -> re-review -> COMPLETED."""
        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_serp = AsyncMock()
        mock_serp.search = AsyncMock(return_value=_make_serp_data())

        failing_pair = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=0.0, feedback="shallow"),
            ScoreDimension(name="differentiation", score=0.0, feedback="weak"),
        ])
        passing_pair = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=1.0, feedback="excellent"),
            ScoreDimension(name="differentiation", score=1.0, feedback="excellent"),
        ])

        score_call = {"count": 0}

        def smart_structured_factory(model_map):
            async def _mock(prompt, schema, **kwargs):
                if schema == _ScorePair:
                    score_call["count"] += 1
                    # First 3 calls (initial score_step): failing
                    # Next 3 calls (re-score after edit): passing
                    if score_call["count"] <= 3:
                        return failing_pair
                    return passing_pair
                if schema in model_map:
                    return model_map[schema]
                raise ValueError(f"Unexpected schema: {schema}")
            return _mock

        mock_llm.generate_text = AsyncMock(return_value=ARTICLE_MARKDOWN)
        mock_llm.generate_structured = AsyncMock(side_effect=smart_structured_factory({
            CompetitiveAnalysis: _make_analysis(),
            ArticleOutline: _make_outline(),
            SeoMetadata: _make_seo_meta(),
            LinkSuggestions: _make_links(),
            SeoMetaOptions: _make_meta_options(),
            ReviewResult: _make_passing_review(),
        }))

        with (
            patch("app.article.pipeline.settings") as mock_settings,
            patch("app.article.pipeline.get_llm_council", return_value=[mock_llm]),
        ):
            mock_settings.quality_threshold = 0.6
            mock_settings.max_revisions = 2
            _apply_test_settings(mock_settings)
            await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.COMPLETED
        assert refreshed.revision_count == 1

    async def test_edit_loop_exits_on_max_revisions(self, session, sample_job):
        """Edit loop exits after max_revisions even if quality stays below threshold."""
        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_serp = AsyncMock()
        mock_serp.search = AsyncMock(return_value=_make_serp_data())

        always_failing = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=0.0, feedback="shallow"),
            ScoreDimension(name="differentiation", score=0.0, feedback="weak"),
        ])

        mock_llm.generate_text = AsyncMock(return_value=ARTICLE_MARKDOWN)
        mock_llm.generate_structured = AsyncMock(side_effect=_smart_generate_structured({
            CompetitiveAnalysis: _make_analysis(),
            ArticleOutline: _make_outline(),
            SeoMetadata: _make_seo_meta(),
            LinkSuggestions: _make_links(),
            SeoMetaOptions: _make_meta_options(),
            _ScorePair: always_failing,
            ReviewResult: _make_passing_review(),
        }))

        with (
            patch("app.article.pipeline.settings") as mock_settings,
            patch("app.article.pipeline.get_llm_council", return_value=[mock_llm]),
        ):
            mock_settings.quality_threshold = 0.99
            mock_settings.max_revisions = 2
            _apply_test_settings(mock_settings)
            await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.COMPLETED
        assert refreshed.revision_count == 2

    async def test_edit_loop_triggers_on_failing_review(self, session, sample_job):
        """Edit loop triggers when review fails even if quality passes."""
        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_serp = AsyncMock()
        mock_serp.search = AsyncMock(return_value=_make_serp_data())

        perfect_pair = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=1.0, feedback="excellent"),
            ScoreDimension(name="differentiation", score=1.0, feedback="excellent"),
        ])

        review_call = {"count": 0}

        def smart_structured(model_map):
            async def _mock(prompt, schema, **kwargs):
                if schema == ReviewResult:
                    review_call["count"] += 1
                    if review_call["count"] == 1:
                        return _make_failing_review()
                    return _make_passing_review()
                if schema in model_map:
                    return model_map[schema]
                raise ValueError(f"Unexpected schema: {schema}")
            return _mock

        mock_llm.generate_text = AsyncMock(return_value=ARTICLE_MARKDOWN)
        mock_llm.generate_structured = AsyncMock(side_effect=smart_structured({
            CompetitiveAnalysis: _make_analysis(),
            ArticleOutline: _make_outline(),
            SeoMetadata: _make_seo_meta(),
            LinkSuggestions: _make_links(),
            SeoMetaOptions: _make_meta_options(),
            _ScorePair: perfect_pair,
        }))

        with (
            patch("app.article.pipeline.settings") as mock_settings,
            patch("app.article.pipeline.get_llm_council", return_value=[mock_llm]),
        ):
            mock_settings.quality_threshold = 0.3
            mock_settings.max_revisions = 2
            _apply_test_settings(mock_settings)
            await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.COMPLETED
        assert refreshed.revision_count == 1


# --- TestMergeScoreDimensions ---


class TestMergeScoreDimensions:
    def test_single_provider_passthrough(self):
        dims = [
            ScoreDimension(name="depth", score=0.8, feedback="good"),
            ScoreDimension(name="readability", score=0.7, feedback="ok"),
        ]
        merged = _merge_score_dimensions(dims)
        assert len(merged) == 2
        names = {d.name for d in merged}
        assert names == {"depth", "readability"}

    def test_multi_provider_averages(self):
        dims = [
            ScoreDimension(name="depth", score=0.8, feedback="good"),
            ScoreDimension(name="depth", score=0.6, feedback="needs work"),
            ScoreDimension(name="readability", score=0.9, feedback="great"),
            ScoreDimension(name="readability", score=0.7, feedback="ok"),
        ]
        merged = _merge_score_dimensions(dims)
        assert len(merged) == 2
        by_name = {d.name: d for d in merged}
        assert by_name["depth"].score == 0.7
        assert by_name["readability"].score == 0.8
        # Feedback from all providers joined
        assert "good" in by_name["depth"].feedback
        assert "needs work" in by_name["depth"].feedback
        assert "great" in by_name["readability"].feedback
        assert "ok" in by_name["readability"].feedback

    def test_empty_input(self):
        merged = _merge_score_dimensions([])
        assert merged == []


# --- TestMergeReviews ---


class TestMergeReviews:
    def test_both_pass(self):
        r1 = ReviewResult(passed=True, summary="Good.", strengths=["A"], issues=[])
        r2 = ReviewResult(passed=True, summary="Also good.", strengths=["B"], issues=[])
        merged = _merge_reviews([r1, r2])
        assert merged.passed is True
        assert "Good." in merged.summary
        assert "Also good." in merged.summary
        assert merged.strengths == ["A", "B"]
        assert merged.issues == []

    def test_one_has_critical_issue(self):
        r1 = ReviewResult(passed=True, summary="Looks fine.", strengths=["X"], issues=[])
        r2 = ReviewResult(
            passed=False,
            summary="Problems found.",
            strengths=["Y"],
            issues=[
                ReviewIssue(
                    category="accuracy",
                    severity=ReviewSeverity.CRITICAL,
                    description="Factual error",
                    suggestion="Fix the claim",
                ),
            ],
        )
        merged = _merge_reviews([r1, r2])
        assert merged.passed is False
        assert len(merged.issues) == 1
        assert merged.issues[0].severity == ReviewSeverity.CRITICAL

    def test_deduplicates_strengths(self):
        r1 = ReviewResult(
            passed=True, summary="A.",
            strengths=["Good structure", "Clear"], issues=[],
        )
        r2 = ReviewResult(
            passed=True, summary="B.",
            strengths=["Good structure", "Thorough"], issues=[],
        )
        merged = _merge_reviews([r1, r2])
        assert merged.strengths == ["Good structure", "Clear", "Thorough"]

    def test_minor_only_passes(self):
        r1 = ReviewResult(passed=True, summary="OK.", strengths=[], issues=[])
        r2 = ReviewResult(
            passed=False,
            summary="Minor issues.",
            strengths=[],
            issues=[
                ReviewIssue(
                    category="style",
                    severity=ReviewSeverity.MINOR,
                    description="Tone inconsistency",
                    suggestion="Adjust tone",
                ),
            ],
        )
        merged = _merge_reviews([r1, r2])
        assert merged.passed is True
        assert len(merged.issues) == 1


# --- TestMultiProviderScoring ---


class TestMultiProviderScoring:
    async def test_both_providers_average_dimensions(
        self, session, sample_job, sample_serp_data, sample_analysis,
        sample_outline, sample_article, sample_seo_metadata,
        sample_keyword_analysis, sample_links,
    ):
        """When both providers succeed, LLM dimensions should be averaged."""
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        sample_job.set_outline(sample_outline)
        sample_job.set_article(sample_article)
        sample_job.set_seo_metadata(sample_seo_metadata)
        sample_job.set_keyword_analysis(sample_keyword_analysis)
        sample_job.set_links(sample_links)
        session.add(sample_job)
        await session.commit()

        from app.article.pipeline import score_step

        primary_pair = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=0.8, feedback="good from claude"),
            ScoreDimension(name="differentiation", score=0.7, feedback="ok from claude"),
        ])
        secondary_pair = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=0.6, feedback="decent from gemini"),
            ScoreDimension(name="differentiation", score=0.9, feedback="great from gemini"),
        ])

        mock_primary = AsyncMock()
        mock_primary.drain_usage = MagicMock(return_value=[])
        mock_primary.drain_call_log = MagicMock(return_value=[])
        mock_secondary = AsyncMock()
        mock_secondary.drain_usage = MagicMock(return_value=[])
        mock_secondary.drain_call_log = MagicMock(return_value=[])
        mock_primary.generate_structured = AsyncMock(return_value=primary_pair)
        mock_secondary.generate_structured = AsyncMock(return_value=secondary_pair)

        with patch(
            "app.article.pipeline.get_llm_council",
            return_value=[mock_primary, mock_secondary],
        ):
            await score_step(sample_job, session, mock_primary, AsyncMock())

        quality = sample_job.get_quality()
        assert quality is not None
        depth = next(d for d in quality.dimensions if d.name == "content_depth")
        diff = next(d for d in quality.dimensions if d.name == "differentiation")
        # Averaged: (0.8*3 + 0.6*3) / 6 = 0.7, (0.7*3 + 0.9*3) / 6 = 0.8
        assert depth.score == 0.7
        assert diff.score == 0.8

    async def test_secondary_fails_uses_primary(
        self, session, sample_job, sample_serp_data, sample_analysis,
        sample_outline, sample_article, sample_seo_metadata,
        sample_keyword_analysis, sample_links,
    ):
        """When secondary provider fails, primary dimensions used alone."""
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        sample_job.set_outline(sample_outline)
        sample_job.set_article(sample_article)
        sample_job.set_seo_metadata(sample_seo_metadata)
        sample_job.set_keyword_analysis(sample_keyword_analysis)
        sample_job.set_links(sample_links)
        session.add(sample_job)
        await session.commit()

        from app.article.pipeline import score_step

        primary_pair = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=0.8, feedback="good"),
            ScoreDimension(name="differentiation", score=0.7, feedback="ok"),
        ])

        mock_primary = AsyncMock()
        mock_primary.drain_usage = MagicMock(return_value=[])
        mock_primary.drain_call_log = MagicMock(return_value=[])
        mock_secondary = AsyncMock()
        mock_secondary.drain_usage = MagicMock(return_value=[])
        mock_secondary.drain_call_log = MagicMock(return_value=[])
        mock_primary.generate_structured = AsyncMock(return_value=primary_pair)
        mock_secondary.generate_structured = AsyncMock(
            side_effect=Exception("Gemini down"),
        )

        with patch(
            "app.article.pipeline.get_llm_council",
            return_value=[mock_primary, mock_secondary],
        ):
            await score_step(sample_job, session, mock_primary, AsyncMock())

        quality = sample_job.get_quality()
        assert quality is not None
        depth = next(d for d in quality.dimensions if d.name == "content_depth")
        assert depth.score == 0.8  # Not averaged, primary only


# --- TestMultiProviderReview ---


class TestMultiProviderReview:
    async def test_both_reviews_merged(
        self, session, sample_job, sample_serp_data, sample_analysis,
        sample_outline, sample_article, sample_seo_metadata,
        sample_keyword_analysis, sample_links,
    ):
        """When both providers review, issues merged and strengths deduped."""
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        sample_job.set_outline(sample_outline)
        sample_job.set_article(sample_article)
        sample_job.set_seo_metadata(sample_seo_metadata)
        sample_job.set_keyword_analysis(sample_keyword_analysis)
        sample_job.set_links(sample_links)
        session.add(sample_job)
        await session.commit()

        from app.article.pipeline import review_step

        review_1 = ReviewResult(
            passed=True, summary="Looks good.",
            issues=[], strengths=["Good structure"],
        )
        review_2 = ReviewResult(
            passed=True, summary="Well done.",
            issues=[ReviewIssue(
                category="tone", severity=ReviewSeverity.MINOR,
                description="Minor tone issue", suggestion="Polish",
            )],
            strengths=["Good structure", "Strong SEO"],
        )

        mock_primary = AsyncMock()
        mock_primary.drain_usage = MagicMock(return_value=[])
        mock_primary.drain_call_log = MagicMock(return_value=[])
        mock_secondary = AsyncMock()
        mock_secondary.drain_usage = MagicMock(return_value=[])
        mock_secondary.drain_call_log = MagicMock(return_value=[])
        mock_primary.generate_structured = AsyncMock(return_value=review_1)
        mock_secondary.generate_structured = AsyncMock(return_value=review_2)

        with patch(
            "app.article.pipeline.get_llm_council",
            return_value=[mock_primary, mock_secondary],
        ):
            await review_step(sample_job, session, mock_primary, AsyncMock())

        review = sample_job.get_review()
        assert review is not None
        assert len(review.issues) == 1
        assert "Good structure" in review.strengths
        assert "Strong SEO" in review.strengths
        assert review.strengths.count("Good structure") == 1


# --- TestSingleProviderFallback ---


class TestSingleProviderFallback:
    async def test_scoring_without_secondary(
        self, session, sample_job, sample_serp_data, sample_analysis,
        sample_outline, sample_article, sample_seo_metadata,
        sample_keyword_analysis, sample_links,
    ):
        """Scoring works with a single-provider council."""
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        sample_job.set_outline(sample_outline)
        sample_job.set_article(sample_article)
        sample_job.set_seo_metadata(sample_seo_metadata)
        sample_job.set_keyword_analysis(sample_keyword_analysis)
        sample_job.set_links(sample_links)
        session.add(sample_job)
        await session.commit()

        from app.article.pipeline import score_step

        pair = _ScorePair(dimensions=[
            ScoreDimension(name="content_depth", score=0.9, feedback="good"),
            ScoreDimension(name="differentiation", score=0.85, feedback="ok"),
        ])

        mock_llm = AsyncMock()
        mock_llm.drain_usage = MagicMock(return_value=[])
        mock_llm.drain_call_log = MagicMock(return_value=[])
        mock_llm.generate_structured = AsyncMock(return_value=pair)

        with patch("app.article.pipeline.get_llm_council", return_value=[mock_llm]):
            await score_step(sample_job, session, mock_llm, AsyncMock())

        quality = sample_job.get_quality()
        assert quality is not None
        # 7 algo + 2 merged LLM (single-provider council)
        assert len(quality.dimensions) == 9
        depth = next(d for d in quality.dimensions if d.name == "content_depth")
        assert depth.score == 0.9
