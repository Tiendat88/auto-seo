"""Tests for the pipeline runner — state transitions, resume, revision loop."""

from unittest.mock import AsyncMock

from app.article.models import (
    ArticleOutline,
    CompetitiveAnalysis,
    CompetitorTheme,
    ExternalReference,
    FaqItem,
    HeadingLevel,
    InternalLink,
    KeywordCluster,
    LinkSuggestions,
    OutlineHeading,
    ScoreDimension,
    SeoMetadata,
)
from app.article.pipeline import (
    _determine_resume_index,
    _FaqList,
    _LlmScoreList,
    run_pipeline,
)
from app.job.models import Job, JobStatus
from app.serp.models import SerpData, SerpResult


def _make_outline() -> ArticleOutline:
    return ArticleOutline(
        h1="Test Article",
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


def _make_faq_list() -> _FaqList:
    return _FaqList(items=[FaqItem(question="What is test?", answer="Test answer.")])


def _make_passing_llm_scores() -> _LlmScoreList:
    return _LlmScoreList(dimensions=[
        ScoreDimension(name="content_depth", score=0.9, feedback="good"),
        ScoreDimension(name="readability", score=0.8, feedback="ok"),
    ])


def _smart_generate_structured(model_map: dict):
    """Return a mock that dispatches based on the schema type."""
    async def _mock(prompt, schema, **kwargs):
        if schema in model_map:
            return model_map[schema]
        raise ValueError(f"Unexpected schema: {schema}")
    return _mock


class TestResumeIndex:
    async def test_empty_job_starts_at_zero(self, sample_job):
        assert _determine_resume_index(sample_job) == 0

    async def test_job_with_serp_starts_at_one(self, sample_job, sample_serp_data):
        sample_job.set_serp(sample_serp_data)
        assert _determine_resume_index(sample_job) == 1

    async def test_job_with_all_data_returns_length(
        self, sample_job, sample_serp_data, sample_analysis, sample_outline,
        sample_article, sample_seo_metadata, sample_keyword_analysis, sample_links
    ):
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        sample_job.set_outline(sample_outline)
        sample_job.set_article(sample_article)
        sample_job.set_seo_metadata(sample_seo_metadata)
        sample_job.set_keyword_analysis(sample_keyword_analysis)
        sample_job.set_links(sample_links)
        # Quality data still missing
        assert _determine_resume_index(sample_job) == 4  # scoring step


class TestPipelineExecution:
    async def test_pipeline_completes_with_mocks(self, session, sample_job):
        """Pipeline should run all steps and set status to COMPLETED."""
        mock_llm = AsyncMock()
        mock_serp = AsyncMock()

        mock_serp.search = AsyncMock(return_value=_make_serp_data())
        mock_llm.generate_text = AsyncMock(return_value="Test content with test keyword. " * 20)
        mock_llm.generate_structured = AsyncMock(side_effect=_smart_generate_structured({
            CompetitiveAnalysis: _make_analysis(),
            ArticleOutline: _make_outline(),
            _FaqList: _make_faq_list(),
            SeoMetadata: _make_seo_meta(),
            LinkSuggestions: _make_links(),
            _LlmScoreList: _make_passing_llm_scores(),
        }))

        await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.COMPLETED
        assert refreshed.serp_data is not None
        assert refreshed.analysis_data is not None
        assert refreshed.outline_data is not None
        assert refreshed.article_data is not None
        assert refreshed.quality_data is not None

    async def test_pipeline_handles_step_failure(self, session, sample_job):
        """Pipeline should set FAILED status on exception."""
        mock_llm = AsyncMock()
        mock_serp = AsyncMock()
        mock_serp.search = AsyncMock(side_effect=Exception("SERP API down"))

        await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.FAILED
        assert "SERP API down" in refreshed.error

    async def test_pipeline_resumes_from_last_step(
        self, session, sample_job, sample_serp_data, sample_analysis
    ):
        """Pipeline should skip already-completed steps on resume."""
        sample_job.set_serp(sample_serp_data)
        sample_job.set_analysis(sample_analysis)
        session.add(sample_job)
        await session.commit()

        mock_llm = AsyncMock()
        mock_serp = AsyncMock()

        outline = _make_outline()
        outline.faq_questions = []  # No FAQ to simplify

        mock_llm.generate_text = AsyncMock(return_value="Content with test keyword. " * 30)
        mock_llm.generate_structured = AsyncMock(side_effect=_smart_generate_structured({
            ArticleOutline: outline,
            SeoMetadata: _make_seo_meta(),
            LinkSuggestions: _make_links(),
            _LlmScoreList: _make_passing_llm_scores(),
        }))

        await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        mock_serp.search.assert_not_called()
        assert refreshed.status == JobStatus.COMPLETED

    async def test_nonexistent_job_does_nothing(self, session):
        """Pipeline should log error for missing job."""
        mock_llm = AsyncMock()
        mock_serp = AsyncMock()

        await run_pipeline("nonexistent-id", session, mock_llm, mock_serp)
        mock_serp.search.assert_not_called()


class TestRevisionLoop:
    async def test_revision_triggered_on_low_quality(self, session, sample_job):
        """Pipeline should re-generate when quality is below threshold."""
        mock_llm = AsyncMock()
        mock_serp = AsyncMock()

        mock_serp.search = AsyncMock(return_value=_make_serp_data())

        failing_scores = _LlmScoreList(dimensions=[
            ScoreDimension(name="content_depth", score=0.2, feedback="too shallow"),
            ScoreDimension(name="readability", score=0.3, feedback="poor"),
        ])
        passing_scores = _LlmScoreList(dimensions=[
            ScoreDimension(name="content_depth", score=1.0, feedback="excellent"),
            ScoreDimension(name="readability", score=1.0, feedback="excellent"),
        ])

        score_call = {"count": 0}

        # Build an outline with enough headings (3 H2s) and many FAQ questions
        revision_outline = ArticleOutline(
            h1="Test Article",
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
                OutlineHeading(
                    level=HeadingLevel.H2, text="Section 3", target_word_count=200,
                    key_points=["point3"], keywords_to_include=["test"],
                ),
            ],
            estimated_total_words=1500,
            faq_questions=["What is test?", "Why test?", "How to test?", "When test?"],
        )

        revision_faq = _FaqList(items=[
            FaqItem(question="What is test?", answer="Test answer one."),
            FaqItem(question="Why test?", answer="Test answer two."),
            FaqItem(question="How to test?", answer="Test answer three."),
            FaqItem(question="When test?", answer="Test answer four."),
        ])

        revision_seo = SeoMetadata(
            title_tag="Test Article Title for Testing Purposes",
            meta_description=(
                "A comprehensive test meta description for the article"
                " about testing purposes and strategies."
            ),
            primary_keyword="test",
            slug="test-article",
        )

        def smart_structured(model_map_first):
            """Return failing scores on first pass, passing on retry."""
            async def _mock(prompt, schema, **kwargs):
                if schema == _LlmScoreList:
                    score_call["count"] += 1
                    if score_call["count"] == 1:
                        return failing_scores
                    return passing_scores
                if schema in model_map_first:
                    return model_map_first[schema]
                raise ValueError(f"Unexpected schema: {schema}")
            return _mock

        # Content with "test" once per 12 words; 4 sections * ~456 words
        section_text = (
            "This is sample content about test topics"
            " written for our article draft. " * 38
        )
        mock_llm.generate_text = AsyncMock(return_value=section_text)
        mock_llm.generate_structured = AsyncMock(side_effect=smart_structured(
            {
                CompetitiveAnalysis: _make_analysis(),
                ArticleOutline: revision_outline,
                _FaqList: revision_faq,
                SeoMetadata: revision_seo,
                LinkSuggestions: _make_links(),
            },
        ))

        await run_pipeline(sample_job.id, session, mock_llm, mock_serp)

        refreshed = await session.get(Job, sample_job.id)
        assert refreshed.status == JobStatus.COMPLETED
        assert refreshed.revision_count == 1
