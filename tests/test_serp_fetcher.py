"""Tests for Firecrawl SDK integration wrappers."""

from types import SimpleNamespace

import pytest

from app.serp import fetcher


class _FakeFirecrawl:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def scrape(self, url: str, **kwargs: object) -> SimpleNamespace:
        self.calls.append((url, kwargs))
        return SimpleNamespace(
            markdown="alpha beta gamma",
            html="<main><p>alpha beta gamma</p></main>",
            metadata=SimpleNamespace(
                title="Example",
                description="Desc",
                language="en",
                statusCode=200,
            ),
        )


@pytest.mark.asyncio
async def test_fetch_page_content_uses_latest_firecrawl_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeFirecrawl()
    monkeypatch.setattr(fetcher, "_get_app", lambda: fake)

    content, word_count = await fetcher.fetch_page_content("https://example.com")

    assert content == "alpha beta gamma"
    assert word_count == 3
    assert len(fake.calls) == 1
    url, kwargs = fake.calls[0]
    assert url == "https://example.com"
    assert kwargs["formats"] == ["markdown"]
    assert kwargs["only_main_content"] is True
    assert "onlyMainContent" not in kwargs


@pytest.mark.asyncio
async def test_fetch_page_full_uses_latest_firecrawl_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeFirecrawl()
    monkeypatch.setattr(fetcher, "_get_app", lambda: fake)

    result = await fetcher.fetch_page_full("https://example.com")

    assert result == {
        "html": "<main><p>alpha beta gamma</p></main>",
        "markdown": "alpha beta gamma",
        "metadata": {
            "title": "Example",
            "description": "Desc",
            "language": "en",
            "status_code": 200,
        },
    }
    assert len(fake.calls) == 1
    url, kwargs = fake.calls[0]
    assert url == "https://example.com"
    assert kwargs["formats"] == ["markdown", "html"]
    assert kwargs["only_main_content"] is True
    assert "onlyMainContent" not in kwargs
