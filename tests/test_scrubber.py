"""Tests for content scrubber post-processing."""

from app.article.models import ArticleContent, ArticleSection, FaqItem, HeadingLevel
from app.article.scrubber import scrub_article


class TestZeroWidthRemoval:
    def test_strips_zero_width_chars(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content="Hello\u200b world\u200c test\u200d content\ufeff here.",
                )
            ]
        )
        result = scrub_article(article)
        assert "\u200b" not in result.sections[0].content
        assert "\u200c" not in result.sections[0].content
        assert "\u200d" not in result.sections[0].content
        assert "\ufeff" not in result.sections[0].content
        assert "Hello world test content here." in result.sections[0].content


class TestEmDashReplacement:
    def test_replaces_em_dashes(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content="First point\u2014second point\u2014third point.",
                )
            ]
        )
        result = scrub_article(article)
        assert "\u2014" not in result.sections[0].content
        assert " -- " in result.sections[0].content


class TestFillerPhraseRemoval:
    def test_removes_opener_fillers(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=(
                        "In today's digital landscape, teams need better tools. "
                        "It's worth noting that productivity matters. "
                        "It's important to note that results vary."
                    ),
                )
            ]
        )
        result = scrub_article(article)
        text = result.sections[0].content
        assert "In today's digital landscape" not in text
        assert "It's worth noting that" not in text
        assert "It's important to note that" not in text

    def test_preserves_normal_content(self):
        content = "Teams need better tools. Productivity matters. Results vary."
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=content,
                )
            ]
        )
        result = scrub_article(article)
        assert "Teams need better tools" in result.sections[0].content


class TestWordSubstitutions:
    def test_replaces_ai_words(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=(
                        "Teams leverage AI to delve into productivity. "
                        "The tapestry of tools helps navigate challenges. "
                        "This holistic paradigm creates synergy."
                    ),
                )
            ]
        )
        result = scrub_article(article)
        text = result.sections[0].content
        assert "leverage" not in text.lower()
        assert "delve" not in text.lower()
        assert "tapestry" not in text.lower()
        assert "paradigm" not in text.lower()
        assert "synergy" not in text.lower()
        assert "holistic" not in text.lower()
        assert "use" in text.lower()
        assert "explore" in text.lower()


class TestParagraphSplitting:
    def test_splits_long_paragraphs(self):
        long_para = (
            "First sentence here. Second sentence here. "
            "Third sentence here. Fourth sentence here. "
            "Fifth sentence here. Sixth sentence here."
        )
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=long_para,
                )
            ]
        )
        result = scrub_article(article)
        paragraphs = result.sections[0].content.split("\n\n")
        assert len(paragraphs) >= 2

    def test_preserves_short_paragraphs(self):
        short = "First sentence. Second sentence. Third sentence."
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=short,
                )
            ]
        )
        result = scrub_article(article)
        paragraphs = result.sections[0].content.split("\n\n")
        assert len(paragraphs) == 1


class TestFaqScrubbing:
    def test_scrubs_faq_answers(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content="Normal content here.",
                )
            ],
            faq=[
                FaqItem(
                    question="What is this?",
                    answer="In today's digital landscape, this leverage\u200bs AI.",
                )
            ],
        )
        result = scrub_article(article)
        answer = result.faq[0].answer
        assert "In today's digital landscape" not in answer
        assert "\u200b" not in answer


class TestCleanPassthrough:
    def test_clean_content_unchanged(self):
        content = "This is clean content with no AI artifacts. It reads naturally."
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test",
                    heading_level=HeadingLevel.H2,
                    content=content,
                )
            ]
        )
        result = scrub_article(article)
        assert result.sections[0].content == content
