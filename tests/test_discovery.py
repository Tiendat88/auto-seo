"""Tests for brand discovery — company extraction, competitor ID, prompt generation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.brand.discovery as discovery_mod
from app.brand.discovery import (
    CompanyInfo,
    CompetitorDiscovery,
    GeneratedPrompt,
    IdentifiedCompetitor,
    PromptCategory,
    generate_brand_prompts,
    identify_competitors,
    scrape_company_info,
)
from app.errors import ContentFetchError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_COMPANY = CompanyInfo(
    name="Notion",
    description="All-in-one workspace for notes, docs, and project management.",
    industry="productivity",
    keywords=["note-taking", "project management", "collaboration", "wiki"],
    main_products=["Notion Workspace", "Notion AI", "Notion Calendar"],
    known_competitors=["Obsidian", "Evernote"],
)

SAMPLE_COMPETITORS = CompetitorDiscovery(
    competitors=[
        IdentifiedCompetitor(
            name="Coda", competitor_type="direct",
            market_overlap="high", confidence=0.9,
        ),
        IdentifiedCompetitor(
            name="Monday.com", competitor_type="direct",
            market_overlap="high", confidence=0.85,
        ),
        IdentifiedCompetitor(
            name="Clickup", competitor_type="direct",
            market_overlap="high", confidence=0.8,
        ),
        IdentifiedCompetitor(
            name="Trello", competitor_type="direct",
            market_overlap="medium", confidence=0.75,
        ),
        IdentifiedCompetitor(
            name="Google Docs", competitor_type="indirect",
            market_overlap="medium", confidence=0.7,
        ),
        IdentifiedCompetitor(
            name="Slack", competitor_type="indirect",
            market_overlap="low", confidence=0.5,
        ),
    ],
)


def _mock_llm(structured_result: object) -> MagicMock:
    llm = MagicMock()
    llm.model_name = "test-model"
    llm.generate_structured = AsyncMock(return_value=structured_result)
    return llm


# ---------------------------------------------------------------------------
# Prompt generation (pure, no LLM)
# ---------------------------------------------------------------------------


class TestGenerateBrandPrompts:
    def test_generates_prompts(self) -> None:
        prompts = generate_brand_prompts(SAMPLE_COMPANY, ["Obsidian", "Evernote", "Coda"])
        assert len(prompts) > 0
        assert all(isinstance(p, GeneratedPrompt) for p in prompts)

    def test_all_categories_represented(self) -> None:
        prompts = generate_brand_prompts(SAMPLE_COMPANY, ["Obsidian", "Evernote", "Coda"])
        categories = {p.category for p in prompts}
        assert PromptCategory.RANKING in categories
        assert PromptCategory.COMPARISON in categories
        assert PromptCategory.ALTERNATIVES in categories
        assert PromptCategory.RECOMMENDATIONS in categories

    def test_max_prompts_respected(self) -> None:
        prompts = generate_brand_prompts(SAMPLE_COMPANY, ["A", "B", "C"], max_prompts=5)
        assert len(prompts) <= 5

    def test_comparison_uses_competitors(self) -> None:
        prompts = generate_brand_prompts(SAMPLE_COMPANY, ["Obsidian", "Evernote"])
        comparison = [p for p in prompts if p.category == PromptCategory.COMPARISON]
        assert len(comparison) > 0
        comparison_text = " ".join(p.prompt for p in comparison)
        assert "Obsidian" in comparison_text or "Evernote" in comparison_text

    def test_no_competitors_still_works(self) -> None:
        prompts = generate_brand_prompts(SAMPLE_COMPANY, [])
        assert len(prompts) > 0
        # Should still have ranking, alternatives, recommendations
        categories = {p.category for p in prompts}
        assert PromptCategory.RANKING in categories

    def test_industry_in_prompts(self) -> None:
        prompts = generate_brand_prompts(SAMPLE_COMPANY, [])
        texts = [p.prompt for p in prompts]
        assert any("productivity" in t for t in texts)

    def test_brand_in_alternatives(self) -> None:
        prompts = generate_brand_prompts(SAMPLE_COMPANY, [])
        alternatives = [p for p in prompts if p.category == PromptCategory.ALTERNATIVES]
        assert all("Notion" in p.prompt for p in alternatives)


# ---------------------------------------------------------------------------
# Company info extraction (mocked Firecrawl + LLM)
# ---------------------------------------------------------------------------


class TestScrapeCompanyInfo:
    async def test_extracts_company_info(self) -> None:
        llm = _mock_llm(SAMPLE_COMPANY)
        with patch.object(discovery_mod, "settings") as mock_settings:
            mock_settings.firecrawl_api_key = "test-key"
            with patch.object(
                discovery_mod, "fetch_page_content",
                new_callable=AsyncMock,
                return_value=("Notion is an all-in-one workspace " * 10, 80),
            ):
                result = await scrape_company_info("https://notion.so", llm)

        assert result.name == "Notion"
        assert result.industry == "productivity"
        llm.generate_structured.assert_called_once()

    async def test_raises_on_missing_firecrawl_key(self) -> None:
        llm = _mock_llm(SAMPLE_COMPANY)
        with patch.object(discovery_mod, "settings") as mock_settings:
            mock_settings.firecrawl_api_key = ""
            with pytest.raises(ContentFetchError, match="FIRECRAWL_API_KEY"):
                await scrape_company_info("https://notion.so", llm)

    async def test_raises_on_short_content(self) -> None:
        llm = _mock_llm(SAMPLE_COMPANY)
        with patch.object(discovery_mod, "settings") as mock_settings:
            mock_settings.firecrawl_api_key = "test-key"
            with patch.object(
                discovery_mod, "fetch_page_content",
                new_callable=AsyncMock,
                return_value=("short", 1),
            ):
                with pytest.raises(ContentFetchError, match="too short"):
                    await scrape_company_info("https://notion.so", llm)

    async def test_raises_on_fetch_failure(self) -> None:
        llm = _mock_llm(SAMPLE_COMPANY)
        with patch.object(discovery_mod, "settings") as mock_settings:
            mock_settings.firecrawl_api_key = "test-key"
            with patch.object(
                discovery_mod, "fetch_page_content",
                new_callable=AsyncMock,
                side_effect=TimeoutError("timeout"),
            ):
                with pytest.raises(ContentFetchError, match="Failed to scrape"):
                    await scrape_company_info("https://notion.so", llm)


# ---------------------------------------------------------------------------
# Competitor identification (mocked LLM)
# ---------------------------------------------------------------------------


class TestIdentifyCompetitors:
    async def test_identifies_competitors(self) -> None:
        llm = _mock_llm(SAMPLE_COMPETITORS)
        result = await identify_competitors(SAMPLE_COMPANY, llm)

        assert len(result) > 0
        names = {c.name for c in result}
        assert "Coda" in names

    async def test_merges_known_competitors(self) -> None:
        llm = _mock_llm(SAMPLE_COMPETITORS)
        result = await identify_competitors(SAMPLE_COMPANY, llm)

        names = {c.name for c in result}
        # Obsidian and Evernote from known_competitors should be included
        assert "Obsidian" in names
        assert "Evernote" in names

    async def test_filters_low_overlap(self) -> None:
        llm = _mock_llm(SAMPLE_COMPETITORS)
        result = await identify_competitors(SAMPLE_COMPANY, llm)

        # "Slack" has low overlap and is indirect → should be filtered
        names = {c.name for c in result}
        assert "Slack" not in names

    async def test_caps_at_nine(self) -> None:
        # Even with many competitors, should cap at 9
        many = CompetitorDiscovery(
            competitors=[
                IdentifiedCompetitor(
                    name=f"Company{i}", competitor_type="direct",
                    market_overlap="high", confidence=0.9,
                )
                for i in range(20)
            ],
        )
        llm = _mock_llm(many)
        company = SAMPLE_COMPANY.model_copy(update={"known_competitors": []})
        result = await identify_competitors(company, llm)
        assert len(result) <= 9
