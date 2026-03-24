"""Fetch AI platform responses via browser automation (Playwright).

Uses real web UIs — no API keys needed, responses match what a real user sees.
Slower than API calls but gives the most authentic platform responses.
"""

import asyncio
import logging

from playwright.async_api import BrowserContext, async_playwright

from app.brand.models import PlatformResponse
from app.errors import LlmError

log = logging.getLogger(__name__)

_BROWSER_ARGS = ["--disable-blink-features=AutomationControlled"]
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


async def _new_context(
    playwright_instance,  # type: ignore[no-untyped-def]
    headless: bool = False,
) -> BrowserContext:
    browser = await playwright_instance.chromium.launch(
        headless=headless, args=_BROWSER_ARGS,
    )
    return await browser.new_context(user_agent=_USER_AGENT)


async def _extract_text(page, selectors: list[str]) -> str:  # type: ignore[no-untyped-def]
    """Try selectors in order, return text from the first match with content."""
    for sel in selectors:
        el = await page.query_selector(sel)
        if el:
            text = (await el.inner_text()).strip()
            if len(text) > 50:
                return text
    return ""


# ---------------------------------------------------------------------------
# Per-platform fetchers
# ---------------------------------------------------------------------------


async def _fetch_perplexity(ctx: BrowserContext, query: str) -> PlatformResponse:
    page = await ctx.new_page()
    try:
        await page.goto("https://www.perplexity.ai/", timeout=30000)
        await page.wait_for_timeout(6000)

        inputs = await page.query_selector_all(
            "textarea, input[type=text], [contenteditable=true]"
        )
        if not inputs:
            raise LlmError("Perplexity: no input field found")

        await inputs[0].click()
        await inputs[0].fill(query)
        await page.wait_for_timeout(300)
        await page.keyboard.press("Enter")

        # Wait for navigation to search results page
        await page.wait_for_url("**/search/**", timeout=15000)
        # Wait for answer to stream in
        await page.wait_for_timeout(12000)

        # .prose contains just the answer text, no nav/chrome
        text = await _extract_text(page, [".prose", "article", "main"])
        if not text:
            raise LlmError("Perplexity: empty response")

        log.info("Perplexity browser: %d chars", len(text))
        return PlatformResponse(platform="perplexity", response_text=text)
    finally:
        await page.close()


async def _fetch_chatgpt(ctx: BrowserContext, query: str) -> PlatformResponse:
    page = await ctx.new_page()
    try:
        await page.goto("https://chatgpt.com/", timeout=30000)
        await page.wait_for_timeout(5000)

        textarea = await page.query_selector("#prompt-textarea")
        if not textarea:
            raise LlmError("ChatGPT: no prompt textarea found")

        await textarea.click()
        await textarea.fill(query)
        await page.wait_for_timeout(300)

        send = await page.query_selector(
            'button[data-testid="send-button"]'
        )
        if send:
            await send.click()
        else:
            await page.keyboard.press("Enter")

        # Wait for assistant response to finish streaming
        await page.wait_for_timeout(20000)

        # Get the last assistant message's markdown content
        msgs = await page.query_selector_all(
            '[data-message-author-role="assistant"]'
        )
        if not msgs:
            raise LlmError("ChatGPT: no assistant response found")

        # .markdown inside the message gives clean content without UI chrome
        md = await msgs[-1].query_selector(".markdown, .prose")
        if md:
            text = (await md.inner_text()).strip()
        else:
            text = (await msgs[-1].inner_text()).strip()

        if not text:
            raise LlmError("ChatGPT: empty response")

        log.info("ChatGPT browser: %d chars", len(text))
        return PlatformResponse(platform="chatgpt", response_text=text)
    finally:
        await page.close()


async def _fetch_gemini(ctx: BrowserContext, query: str) -> PlatformResponse:
    page = await ctx.new_page()
    try:
        await page.goto("https://gemini.google.com/", timeout=30000)
        await page.wait_for_timeout(5000)

        editors = await page.query_selector_all("[contenteditable=true]")
        if not editors:
            raise LlmError("Gemini: no input field found")

        await editors[0].click()
        await page.keyboard.type(query, delay=20)
        await page.wait_for_timeout(300)

        send = await page.query_selector(
            'button[aria-label*="Send"], button[aria-label*="send"]'
        )
        if send:
            await send.click()
        else:
            await page.keyboard.press("Enter")

        # Wait for response to finish streaming
        await page.wait_for_timeout(20000)

        # .model-response-text gives clean answer without "Gemini said" prefix
        text = await _extract_text(page, [
            ".model-response-text",
            "message-content",
            ".markdown",
            ".response-container",
        ])
        if not text:
            raise LlmError("Gemini: empty response")

        log.info("Gemini browser: %d chars", len(text))
        return PlatformResponse(platform="gemini", response_text=text)
    finally:
        await page.close()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_FETCHERS = {
    "perplexity": _fetch_perplexity,
    "chatgpt": _fetch_chatgpt,
    "gemini": _fetch_gemini,
}


async def fetch_browser_responses(
    query: str,
    platforms: list[str] | None = None,
    skip: set[str] | None = None,
) -> list[PlatformResponse]:
    """Fetch responses from AI platforms via browser automation.

    Args:
        query: The search query to submit.
        platforms: Which platforms to query. Defaults to all available.
        skip: Platform names to skip (e.g. user already pasted them).
    """
    skip = skip or set()
    targets = platforms or list(_FETCHERS.keys())
    targets = [t for t in targets if t not in skip]

    if not targets:
        raise ValueError("No platforms to fetch from")

    async with async_playwright() as pw:
        ctx = await _new_context(pw)
        try:
            tasks = {
                name: asyncio.create_task(_FETCHERS[name](ctx, query))
                for name in targets
                if name in _FETCHERS
            }

            results: list[PlatformResponse] = []
            errors: list[str] = []

            for name, task in tasks.items():
                try:
                    results.append(await task)
                except Exception as exc:
                    log.warning("Browser fetch from %s failed: %s", name, exc)
                    errors.append(f"{name}: {exc}")

            if not results:
                raise LlmError(
                    f"All browser fetches failed: {'; '.join(errors)}"
                )
            if errors:
                log.warning(
                    "Some browser fetches failed: %s", "; ".join(errors),
                )

            return results
        finally:
            await ctx.browser.close()  # type: ignore[union-attr]
