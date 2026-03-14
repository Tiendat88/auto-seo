"""Tests for JSON-LD schema markup and snippet detection."""

from app.article.models import (
    ArticleContent,
    ArticleSection,
    CompetitiveAnalysis,
    CompetitorTheme,
    FaqItem,
    HeadingLevel,
    KeywordCluster,
)
from app.article.schema import (
    detect_snippet_opportunities,
    generate_schema_markup,
)


class TestArticleSchema:
    def test_article_schema_structure(
        self, sample_article, sample_seo_metadata, sample_outline
    ):
        markup = generate_schema_markup(sample_article, sample_seo_metadata, sample_outline)
        schema = markup.article_schema
        assert schema["@context"] == "https://schema.org"
        assert schema["@type"] == "Article"
        assert schema["headline"] == sample_seo_metadata.title_tag
        assert schema["description"] == sample_seo_metadata.meta_description
        assert schema["wordCount"] == sample_article.total_word_count
        assert schema["keywords"] == sample_seo_metadata.primary_keyword
        assert len(schema["articleSection"]) == len(sample_article.sections)

    def test_faq_schema_present_when_faq_exists(
        self, sample_article, sample_seo_metadata, sample_outline
    ):
        markup = generate_schema_markup(sample_article, sample_seo_metadata, sample_outline)
        assert markup.faq_schema is not None
        assert markup.faq_schema["@type"] == "FAQPage"
        entities = markup.faq_schema["mainEntity"]
        assert len(entities) == len(sample_article.faq)
        for entity, faq in zip(entities, sample_article.faq):
            assert entity["@type"] == "Question"
            assert entity["name"] == faq.question
            assert entity["acceptedAnswer"]["@type"] == "Answer"
            assert entity["acceptedAnswer"]["text"] == faq.answer

    def test_no_faq_schema_without_faq(self, sample_seo_metadata, sample_outline):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test", heading_level=HeadingLevel.H2, content="Content here."
                )
            ]
        )
        markup = generate_schema_markup(article, sample_seo_metadata, sample_outline)
        assert markup.faq_schema is None


class TestSnippetDetection:
    def _make_analysis(self):
        return CompetitiveAnalysis(
            keywords=KeywordCluster(primary="test"),
            themes=[CompetitorTheme(theme="test", frequency=5, subtopics=[])],
            avg_word_count=1000,
            search_intent="informational",
        )

    def test_detects_list_opportunity(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Steps to Follow",
                    heading_level=HeadingLevel.H2,
                    content="1. First step here. 2. Second step here. 3. Third step.",
                )
            ]
        )
        opps = detect_snippet_opportunities(article, self._make_analysis())
        list_opps = [o for o in opps if o.type == "list"]
        assert len(list_opps) >= 1
        assert not list_opps[0].current_format_ok

    def test_list_with_markdown_is_ok(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Features",
                    heading_level=HeadingLevel.H2,
                    content="Key features:\n- Feature one\n- Feature two\n- Feature three",
                )
            ]
        )
        opps = detect_snippet_opportunities(article, self._make_analysis())
        list_opps = [o for o in opps if o.type == "list"]
        assert any(o.current_format_ok for o in list_opps)

    def test_detects_table_opportunity(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Tool Comparison",
                    heading_level=HeadingLevel.H2,
                    content="Tool A vs Tool B: when compared to alternatives, Tool A is better.",
                )
            ]
        )
        opps = detect_snippet_opportunities(article, self._make_analysis())
        table_opps = [o for o in opps if o.type == "table"]
        assert len(table_opps) >= 1
        assert not table_opps[0].current_format_ok

    def test_detects_definition_snippet(self):
        words_40 = " ".join(["word"] * 40)
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="What is Productivity",
                    heading_level=HeadingLevel.H2,
                    content=f"{words_40}. More content follows here.",
                )
            ]
        )
        opps = detect_snippet_opportunities(article, self._make_analysis())
        def_opps = [o for o in opps if o.type == "definition"]
        assert len(def_opps) == 1
        assert def_opps[0].current_format_ok

    def test_detects_qa_from_faq(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Test", heading_level=HeadingLevel.H2, content="Content."
                )
            ],
            faq=[
                FaqItem(question="What is X?", answer="X is a thing."),
                FaqItem(question="How does Y work?", answer="Y works like this."),
            ],
        )
        opps = detect_snippet_opportunities(article, self._make_analysis())
        qa_opps = [o for o in opps if o.type == "qa"]
        assert len(qa_opps) == 2
        assert all(o.current_format_ok for o in qa_opps)

    def test_no_false_positives_on_clean_content(self):
        article = ArticleContent(
            sections=[
                ArticleSection(
                    heading="Simple Topic",
                    heading_level=HeadingLevel.H2,
                    content="This is a simple paragraph with no special formatting or comparisons.",
                )
            ]
        )
        opps = detect_snippet_opportunities(article, self._make_analysis())
        assert len(opps) == 0
