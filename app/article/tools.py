"""Research tools for LLM tool-use during analysis."""

import json
import logging

log = logging.getLogger(__name__)

RESEARCH_TOOLS = [
    {
        "name": "search_web",
        "description": "Search the web for a query. Returns top results with content.",
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


async def handle_tool_call(name: str, args: dict) -> str:
    """Execute a research tool call and return the result as JSON string."""
    from app.serp.fetcher import fetch_page_content, search_web

    if name == "search_web":
        results = await search_web(args["query"])
        log.info("Tool search_web: %d results for '%s'", len(results), args["query"])
        return json.dumps(results)
    if name == "fetch_url":
        content, wc = await fetch_page_content(args["url"])
        log.info("Tool fetch_url: %d words from %s", wc, args["url"])
        return json.dumps({"content": content, "word_count": wc})
    return json.dumps({"error": f"Unknown tool: {name}"})
