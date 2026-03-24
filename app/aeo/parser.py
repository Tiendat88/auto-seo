"""Content fetching and HTML parsing for AEO analysis."""

import re
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from app.errors import ContentFetchError

_FETCH_TIMEOUT = 10
_BOILERPLATE = {"nav", "footer", "header", "aside", "script", "style", "noscript"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_HTML_DETECT = re.compile(r"<\s*(?:html|head|body|div|p|h[1-6]|span|a)\b", re.IGNORECASE)


@dataclass
class ParsedContent:
    raw: str
    text: str
    first_paragraph: str
    headings: list[tuple[str, str]] = field(default_factory=list)
    is_html: bool = False


async def fetch_url(url: str) -> str:
    """Fetch URL content via httpx. Raises ContentFetchError on failure."""
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


def parse_content(raw: str) -> ParsedContent:
    """Parse HTML or plain text into structured content."""
    if _HTML_DETECT.search(raw):
        return _parse_html(raw)
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


def _parse_plain_text(raw: str) -> ParsedContent:
    parts = re.split(r"\n\s*\n", raw.strip(), maxsplit=1)
    first_paragraph = parts[0].strip() if parts else ""
    text = raw.strip()
    return ParsedContent(
        raw=raw, text=text, first_paragraph=first_paragraph,
        headings=[], is_html=False,
    )


async def get_content(input_type: str, input_value: str) -> ParsedContent:
    """Fetch (if URL) and parse content."""
    if input_type == "url":
        html = await fetch_url(input_value)
        return parse_content(html)
    return parse_content(input_value)
