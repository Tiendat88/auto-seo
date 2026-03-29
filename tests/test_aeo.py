"""Tests for AEO content scoring: parser, checks, aggregation."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.aeo.checks import (
    DirectAnswerAnalysis,
    check_direct_answer,
    check_htag_hierarchy,
    check_readability,
    compute_aeo_score,
)
from app.aeo.parser import ParsedContent, parse_content

FIXTURES = Path(__file__).parent / "fixtures"


def _load_html(name: str) -> str:
    return (FIXTURES / name).read_text()


# --- Content Parser ---


class TestContentParser:
    def test_parse_html_strips_boilerplate(self):
        html = "<html><body><nav>Menu</nav><main><p>Hello</p></main><footer>Foot</footer></body>"
        result = parse_content(html)
        assert result.is_html
        assert "Menu" not in result.text
        assert "Foot" not in result.text
        assert "Hello" in result.text

    def test_parse_html_extracts_first_paragraph(self):
        html = "<html><body><h1>Title</h1><p>First paragraph here.</p><p>Second.</p></body>"
        result = parse_content(html)
        assert result.first_paragraph == "First paragraph here."

    def test_parse_html_extracts_headings_in_order(self):
        html = "<html><body><h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2></body>"
        result = parse_content(html)
        assert result.headings == [("h1", "A"), ("h2", "B"), ("h3", "C"), ("h2", "D")]

    def test_parse_plain_text(self):
        text = "First paragraph.\n\nSecond paragraph."
        result = parse_content(text)
        assert not result.is_html
        assert result.first_paragraph == "First paragraph."
        assert result.headings == []

    def test_parse_article_good(self):
        result = parse_content(_load_html("article_good.html"))
        assert result.is_html
        assert result.headings[0] == ("h1", "What Is Retrieval-Augmented Generation (RAG)?")
        assert len(result.first_paragraph.split()) > 0

    def test_parse_article_bad(self):
        result = parse_content(_load_html("article_bad.html"))
        assert result.is_html
        # First heading is h3, not h1
        assert result.headings[0][0] == "h3"


# --- Check A: Direct Answer ---


def _mock_llm(is_declarative: bool) -> MagicMock:
    """Return a mock LlmClient whose generate_structured returns DirectAnswerAnalysis."""
    llm = MagicMock()
    llm.generate_structured = AsyncMock(
        return_value=DirectAnswerAnalysis(is_declarative=is_declarative, reasoning="test"),
    )
    return llm


class TestDirectAnswer:
    async def test_short_declarative_no_hedge(self):
        content = ParsedContent(
            raw="", text="",
            first_paragraph=(
                "Python is a programming language used for web development and data science."
            ),
            is_html=False,
        )
        result = await check_direct_answer(content, _mock_llm(True))
        assert result.score == 20
        assert result.details["is_declarative"]
        assert not result.details["has_hedge_phrase"]

    async def test_hedge_phrase_penalized(self):
        content = ParsedContent(
            raw="", text="",
            first_paragraph="It depends on the use case whether Python is the right choice.",
            is_html=False,
        )
        result = await check_direct_answer(content, _mock_llm(True))
        assert result.score == 12
        assert result.details["has_hedge_phrase"]

    async def test_long_paragraph_61_to_90_words(self):
        # Build a 75-word paragraph
        words = "The quick brown fox jumps over the lazy dog. " * 9  # ~81 words
        content = ParsedContent(raw="", text="", first_paragraph=words.strip(), is_html=False)
        wc = len(content.first_paragraph.split())
        assert 61 <= wc <= 90
        result = await check_direct_answer(content, _mock_llm(True))
        assert result.score == 8

    async def test_very_long_paragraph_over_90(self):
        words = "This is a word. " * 25  # 100 words
        content = ParsedContent(raw="", text="", first_paragraph=words.strip(), is_html=False)
        assert len(content.first_paragraph.split()) > 90
        result = await check_direct_answer(content, _mock_llm(True))
        assert result.score == 0

    async def test_fragment_no_verb(self):
        content = ParsedContent(
            raw="", text="",
            first_paragraph="A comprehensive overview of modern systems.",
            is_html=False,
        )
        result = await check_direct_answer(content, _mock_llm(False))
        # No root verb → not declarative → 12
        assert result.score == 12
        assert not result.details["is_declarative"]

    async def test_empty_paragraph(self):
        content = ParsedContent(raw="", text="", first_paragraph="", is_html=False)
        result = await check_direct_answer(content, _mock_llm(False))
        assert result.score == 12  # ≤60 words but not declarative

    async def test_article_good_scores_high(self):
        parsed = parse_content(_load_html("article_good.html"))
        result = await check_direct_answer(parsed, _mock_llm(True))
        assert result.score == 20

    async def test_article_bad_scores_low(self):
        parsed = parse_content(_load_html("article_bad.html"))
        result = await check_direct_answer(parsed, _mock_llm(True))
        assert result.score <= 8  # long paragraph with hedging


# --- Check B: H-tag Hierarchy ---


class TestHtagHierarchy:
    def test_valid_hierarchy(self):
        content = ParsedContent(
            raw="", text="",
            first_paragraph="",
            headings=[("h1", "A"), ("h2", "B"), ("h3", "C"), ("h2", "D")],
            is_html=True,
        )
        result = check_htag_hierarchy(content)
        assert result.score == 20
        assert result.details["violations"] == []

    def test_missing_h1(self):
        content = ParsedContent(
            raw="", text="", first_paragraph="",
            headings=[("h2", "A"), ("h3", "B")],
            is_html=True,
        )
        result = check_htag_hierarchy(content)
        assert result.score == 0
        assert any("Missing H1" in v for v in result.details["violations"])

    def test_multiple_h1s(self):
        content = ParsedContent(
            raw="", text="", first_paragraph="",
            headings=[("h1", "A"), ("h2", "B"), ("h1", "C")],
            is_html=True,
        )
        result = check_htag_hierarchy(content)
        assert result.score == 12
        assert any("Multiple H1" in v for v in result.details["violations"])

    def test_skipped_level(self):
        content = ParsedContent(
            raw="", text="", first_paragraph="",
            headings=[("h1", "A"), ("h3", "B")],
            is_html=True,
        )
        result = check_htag_hierarchy(content)
        assert result.score == 12
        assert any("Skipped" in v for v in result.details["violations"])

    def test_heading_before_h1(self):
        content = ParsedContent(
            raw="", text="", first_paragraph="",
            headings=[("h2", "Before"), ("h1", "Title"), ("h2", "After")],
            is_html=True,
        )
        result = check_htag_hierarchy(content)
        assert any("before H1" in v for v in result.details["violations"])

    def test_three_plus_violations_score_zero(self):
        content = ParsedContent(
            raw="", text="", first_paragraph="",
            headings=[("h3", "A"), ("h1", "B"), ("h1", "C"), ("h4", "D")],
            is_html=True,
        )
        result = check_htag_hierarchy(content)
        assert result.score == 0
        assert len(result.details["violations"]) >= 3

    def test_article_good_scores_perfect(self):
        parsed = parse_content(_load_html("article_good.html"))
        result = check_htag_hierarchy(parsed)
        assert result.score == 20

    def test_article_bad_scores_low(self):
        parsed = parse_content(_load_html("article_bad.html"))
        result = check_htag_hierarchy(parsed)
        assert result.score <= 12
        assert len(result.details["violations"]) >= 2


# --- Check C: Readability ---


class TestReadability:
    def test_moderate_grade_scores_well(self):
        # Use article_good.html which is written at a moderate reading level
        parsed = parse_content(_load_html("article_good.html"))
        result = check_readability(parsed)
        grade = result.details["fk_grade_level"]
        # article_good.html should be written accessibly
        assert result.score > 0
        assert grade > 0

    def test_very_complex_text(self):
        text = (
            "The epistemological ramifications of contemporaneous hermeneutical "
            "phenomenological methodologies necessitate a comprehensive reconceptualization "
            "of the multifaceted interdisciplinary paradigmatic frameworks. "
            "Accordingly, the heterogeneous ontological presuppositions undergirding "
            "these sophisticated analytical instrumentalities require systematic "
            "philosophical deconstruction and reconstitution."
        )
        content = ParsedContent(raw="", text=text, first_paragraph="", is_html=False)
        result = check_readability(content)
        assert result.details["fk_grade_level"] >= 12
        assert result.score == 0

    def test_very_simple_text(self):
        text = "I am a cat. I sit. I eat. I run. I sleep. I play. You pet me. I purr."
        content = ParsedContent(raw="", text=text, first_paragraph="", is_html=False)
        result = check_readability(content)
        assert result.details["fk_grade_level"] <= 4
        assert result.score == 0

    def test_complex_sentences_returned(self):
        text = (
            "The cat sat on the mat. "
            "Epistemological hermeneutical phenomenological methodologies are complex. "
            "Dogs run fast. "
            "The multifaceted interdisciplinary paradigmatic framework "
            "requires reconceptualization. "
            "Birds fly high."
        )
        content = ParsedContent(raw="", text=text, first_paragraph="", is_html=False)
        result = check_readability(content)
        complex_sents = result.details["complex_sentences"]
        assert len(complex_sents) <= 3
        # The complex sentences should be the academic ones
        assert any("Epistemological" in s for s in complex_sents)

    def test_insufficient_text(self):
        content = ParsedContent(raw="", text="Too short.", first_paragraph="", is_html=False)
        result = check_readability(content)
        assert result.score == 0
        assert "Insufficient" in (result.recommendation or "")

    def test_article_good_reasonable_score(self):
        parsed = parse_content(_load_html("article_good.html"))
        result = check_readability(parsed)
        assert result.score > 0


# --- Score Aggregation ---


class TestAeoScoring:
    def test_perfect_score(self):
        from app.aeo.models import CheckResult
        checks = [
            CheckResult(check_id="a", name="A", passed=True, score=20, details={}),
            CheckResult(check_id="b", name="B", passed=True, score=20, details={}),
            CheckResult(check_id="c", name="C", passed=True, score=20, details={}),
        ]
        score, band = compute_aeo_score(checks)
        assert score == 100
        assert band == "AEO Optimized"

    def test_zero_score(self):
        from app.aeo.models import CheckResult
        checks = [
            CheckResult(check_id="a", name="A", passed=False, score=0, details={}),
            CheckResult(check_id="b", name="B", passed=False, score=0, details={}),
            CheckResult(check_id="c", name="C", passed=False, score=0, details={}),
        ]
        score, band = compute_aeo_score(checks)
        assert score == 0
        assert band == "Not AEO Ready"

    def test_needs_improvement(self):
        from app.aeo.models import CheckResult
        checks = [
            CheckResult(check_id="a", name="A", passed=False, score=12, details={}),
            CheckResult(check_id="b", name="B", passed=True, score=20, details={}),
            CheckResult(check_id="c", name="C", passed=False, score=14, details={}),
        ]
        score, band = compute_aeo_score(checks)
        # (12+20+14)/60*100 = 76.67 → 77
        assert score == 77
        assert band == "Needs Improvement"

    def test_significant_gaps(self):
        from app.aeo.models import CheckResult
        checks = [
            CheckResult(check_id="a", name="A", passed=False, score=8, details={}),
            CheckResult(check_id="b", name="B", passed=False, score=12, details={}),
            CheckResult(check_id="c", name="C", passed=False, score=8, details={}),
        ]
        score, band = compute_aeo_score(checks)
        # (8+12+8)/60*100 = 46.67 → 47
        assert score == 47
        assert band == "Significant Gaps"
