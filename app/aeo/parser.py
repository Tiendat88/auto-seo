"""Content fetching and HTML parsing for AEO analysis."""

import logging
import re
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.errors import ContentFetchError

log = logging.getLogger(__name__)

_FETCH_TIMEOUT = 10
_BOILERPLATE = {"nav", "footer", "header", "aside", "script", "style", "noscript"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_HTML_DETECT = re.compile(r"<\s*(?:html|head|body|div|p|h[1-6]|span|a)\b", re.IGNORECASE)
_MARKDOWN_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class ParsedContent:
    raw: str
    text: str
    first_paragraph: str
    headings: list[tuple[str, str]] = field(default_factory=list)
    is_html: bool = False
    markdown: str = ""


async def fetch_url(url: str) -> ParsedContent:
    """Fetch and parse URL content. Uses Firecrawl if configured, else httpx."""
    if settings.firecrawl_api_key:
        return await _fetch_firecrawl(url)
    return await _fetch_httpx_cached(url)


async def _fetch_firecrawl(url: str) -> ParsedContent:
    """Fetch via Firecrawl — returns both HTML (for structure) and markdown (for text)."""
    from app.aeo.store import get_cached_fetch, set_cached_fetch
    from app.serp.fetcher import fetch_page_full

    # Check Redis cache first
    cached = await get_cached_fetch(url)
    if cached:
        log.info("Cache hit for %s", url)
        result = cached
    else:
        try:
            result = await fetch_page_full(url)
        except Exception as exc:
            if isinstance(exc, ContentFetchError):
                raise
            raise ContentFetchError(f"Firecrawl fetch failed: {exc}")
        await set_cached_fetch(url, result)

    html = result["html"]
    md = result["markdown"]
    metadata = result["metadata"]

    if not html and not md:
        raise ContentFetchError(f"Firecrawl returned empty content from {url}")

    wc = len(md.split())
    log.info("Firecrawl fetched %d words from %s (lang=%s)", wc, url, metadata.get("language"))

    # HTML for structural checks (headings, first paragraph)
    # Markdown for clean text (readability, gap analysis)
    parsed = _parse_html(html) if html else _parse_markdown(md)
    parsed.markdown = md

    # Override text with markdown-derived clean text (no boilerplate, no HTML noise)
    if md:
        parsed.text = _strip_markdown(md)

    return parsed


async def _fetch_httpx(url: str) -> str:
    """Fetch via httpx — plain HTTP, no JS rendering."""
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.TimeoutException:
        raise ContentFetchError(f"Connection timeout after {_FETCH_TIMEOUT}s")
    except httpx.HTTPStatusError as exc:
        raise ContentFetchError(f"HTTP {exc.response.status_code} from {url}")
    except httpx.RequestError as exc:
        raise ContentFetchError(f"Request failed: {exc}")


async def _fetch_httpx_cached(url: str) -> ParsedContent:
    """Fetch via httpx with Redis cache (7-day TTL)."""
    from app.aeo.store import get_cached_fetch, set_cached_fetch

    cached = await get_cached_fetch(url)
    if cached:
        log.info("Cache hit (httpx) for %s", url)
        raw = cached.get("html") or cached.get("markdown") or ""
        return parse_content(raw)

    raw = await _fetch_httpx(url)
    await set_cached_fetch(url, {"html": raw, "markdown": "", "metadata": {}})
    return parse_content(raw)


def parse_content(raw: str) -> ParsedContent:
    """Parse HTML, markdown, or plain text into structured content."""
    if _HTML_DETECT.search(raw):
        return _parse_html(raw)
    if _MARKDOWN_HEADING.search(raw):
        return _parse_markdown(raw)
    return _parse_plain_text(raw)


def _parse_html(raw: str) -> ParsedContent:
    soup = BeautifulSoup(raw, "html.parser")

    # Strip boilerplate tags
    for tag in soup.find_all(_BOILERPLATE):
        tag.decompose()

    # Extract headings in DOM order
    headings: list[tuple[str, str]] = []
    for tag in soup.find_all(_HEADING_TAGS):
        text = tag.get_text(strip=True)
        if text:
            headings.append((tag.name.lower(), text))

    # First paragraph
    first_p = soup.find("p")
    first_paragraph = first_p.get_text(strip=True) if first_p else ""

    # Clean body text
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()

    return ParsedContent(
        raw=raw, text=text, first_paragraph=first_paragraph,
        headings=headings, is_html=True,
    )


def _parse_markdown(raw: str) -> ParsedContent:
    """Parse markdown into structured content."""
    headings: list[tuple[str, str]] = []
    for match in _MARKDOWN_HEADING.finditer(raw):
        level = len(match.group(1))
        text = match.group(2).strip()
        if text:
            headings.append((f"h{level}", text))

    # First paragraph: first non-heading, non-empty, non-link/image line
    first_paragraph = ""
    for line in raw.strip().split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "[", "!", "|", "---", "```")):
            continue
        first_paragraph = _strip_markdown(stripped)
        break

    return ParsedContent(
        raw=raw, text=_strip_markdown(raw), first_paragraph=first_paragraph,
        headings=headings, is_html=False, markdown=raw,
    )


def _parse_plain_text(raw: str) -> ParsedContent:
    parts = re.split(r"\n\s*\n", raw.strip(), maxsplit=1)
    first_paragraph = parts[0].strip() if parts else ""
    return ParsedContent(
        raw=raw, text=raw.strip(), first_paragraph=first_paragraph,
        headings=[], is_html=False,
    )


def _strip_markdown(text: str) -> str:
    """Strip markdown syntax to get clean text for analysis."""
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links → text
    text = re.sub(r"#{1,6}\s+", "", text)  # heading markers
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)  # bold/italic
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)  # code
    text = re.sub(r"\n\s*\n+", "\n", text)  # collapse blank lines
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def get_content(input_type: str, input_value: str) -> ParsedContent:
    """Fetch (if URL) and parse content."""
    if input_type == "url":
        return await fetch_url(input_value)
    return parse_content(input_value)
