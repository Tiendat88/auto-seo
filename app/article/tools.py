"""Research tools for LLM tool-use during analysis."""

import json
import logging
from urllib.parse import urlparse

log = logging.getLogger(__name__)

RESEARCH_TOOLS = [
    {
        "name": "search_web",
        "description": (
            "Search the web for a query."
            " Returns top results with URL, title, and description."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch a URL and get its content as markdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
            },
            "required": ["url"],
        },
    },
]


async def handle_tool_call(
    name: str, args: dict, allowed_domains: set[str] | None = None,
) -> str:
    """Execute a research tool call and return the result as JSON string."""
    from app.serp.fetcher import fetch_page_content, search_web

    try:
        if name == "search_web":
            query = args.get("query")
            if not query:
                return json.dumps({"error": "Missing or invalid 'query' argument"})
            results = await search_web(query)
            log.info("Tool search_web: %d results for '%s'", len(results), query)
            return json.dumps(results)

        if name == "fetch_url":
            url = args.get("url", "")
            if not url:
                return json.dumps({"error": "Missing or invalid 'url' argument"})
            if allowed_domains:
                domain = urlparse(url).netloc.removeprefix("www.")
                normalized = {d.removeprefix("www.") for d in allowed_domains}
                if domain not in normalized:
                    return json.dumps({"error": f"Domain {domain} not in allowed list"})
            content, wc = await fetch_page_content(url)
            log.info("Tool fetch_url: %d words from %s", wc, url)
            return json.dumps({"content": content, "word_count": wc})

        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        log.warning("Tool %s failed: %s", name, e)
        return json.dumps({"error": f"Tool execution failed: {e}"})
