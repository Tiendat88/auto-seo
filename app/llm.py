import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.cache import cache, cache_key
from app.config import settings
from app.errors import LlmError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try markdown code block first
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try raw JSON (find first { or [)
    for i, ch in enumerate(text):
        if ch in "{[":
            # Find matching close
            depth = 0
            open_ch = ch
            close_ch = "}" if ch == "{" else "]"
            for j in range(i, len(text)):
                if text[j] == open_ch:
                    depth += 1
                elif text[j] == close_ch:
                    depth -= 1
                    if depth == 0:
                        return text[i : j + 1]
            break
    return text.strip()


class LlmClient:
    """LLM client with dual backend: Anthropic API (if key set) or Claude Agent SDK."""

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.llm_model
        self._use_sdk = not self._api_key
        if not self._use_sdk:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)

    async def generate_text(self, prompt: str, max_tokens: int = 4096) -> str:
        """Generate free-form text."""
        try:
            if self._use_sdk:
                return await self._generate_via_sdk(prompt)
            return await self._generate_via_api(prompt, max_tokens)
        except LlmError:
            raise
        except Exception as e:
            raise LlmError(f"LLM text generation failed: {e}") from e

    async def _generate_via_api(self, prompt: str, max_tokens: int) -> str:
        """Generate text via Anthropic API directly."""

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        async def _call() -> str:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            parts = [
                b.text for b in response.content if hasattr(b, "text")
            ]
            if not parts:
                raise LlmError("No text content in API response")
            return "".join(parts)

        return await _call()

    async def _generate_via_sdk(self, prompt: str) -> str:
        """Generate text via Claude Agent SDK (uses Claude Code OAuth)."""
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        async def _call() -> str:
            options = ClaudeAgentOptions(
                disallowed_tools=[
                    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
                    "WebFetch", "WebSearch", "NotebookEdit", "Agent",
                ],
                max_turns=1,
                model=self._model,
                system_prompt=(
                    "You are a direct text generator. "
                    "Respond only with the requested content."
                ),
            )
            result_text = ""
            assistant_text = ""
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            assistant_text += block.text
                elif isinstance(message, ResultMessage):
                    result_text = message.result or ""
                    if message.is_error:
                        log.error(
                            "Agent SDK error (is_error=True): %s",
                            result_text,
                        )
                        raise LlmError(
                            f"Agent SDK error: {result_text}"
                        )
                    log.info(
                        "Agent SDK response: subtype=%s, "
                        "result_len=%d, turns=%s",
                        message.subtype,
                        len(result_text),
                        getattr(message, "num_turns", "?"),
                    )
            final = result_text or assistant_text
            if not final:
                log.error(
                    "Agent SDK empty response. result_len=%d, "
                    "assistant_len=%d, prompt_len=%d",
                    len(result_text),
                    len(assistant_text),
                    len(prompt),
                )
                raise LlmError("No response from Agent SDK")
            return final

        return await _call()

    async def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        max_tokens: int = 4096,
        use_cache: bool = True,
    ) -> T:
        """Generate structured output parsed into a Pydantic model."""
        ck = cache_key("llm", prompt, self._model, schema.__name__)

        if use_cache:
            cached = await cache.get(ck)
            if cached:
                try:
                    log.info("LLM cache hit for schema=%s", schema.__name__)
                    return schema.model_validate_json(cached)
                except ValidationError:
                    log.warning("Stale cache entry for schema=%s, regenerating", schema.__name__)
                    await cache.invalidate(ck)

        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            f"Respond ONLY with valid JSON matching this schema:\n{schema_json}"
        )

        raw = await self.generate_text(full_prompt, max_tokens)
        json_str = _extract_json(raw)

        try:
            result = schema.model_validate_json(json_str)
        except ValidationError as e:
            log.warning("Structured output validation failed, retrying: %s", e)
            retry_prompt = (
                f"Your previous JSON response was invalid:\n{e}\n\n"
                f"Original request:\n{full_prompt}\n\n"
                f"Please fix the JSON and respond with valid JSON only."
            )
            raw = await self.generate_text(retry_prompt, max_tokens)
            json_str = _extract_json(raw)
            try:
                result = schema.model_validate_json(json_str)
            except ValidationError as e2:
                raise LlmError(f"Structured output failed after retry: {e2}") from e2

        if use_cache:
            await cache.set(ck, result.model_dump_json(), ttl=3600)

        return result
