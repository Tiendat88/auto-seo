import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.article.models import TokenUsage
from app.cache import cache, cache_key
from app.config import settings
from app.errors import LlmError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# $/1M tokens (input, output)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "claude-opus-4-6": (15.0, 75.0),
    "o3-mini": (1.10, 4.40),
    "gpt-4o": (2.50, 10.0),
    "gemini-3-pro-preview": (1.25, 10.0),
}


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


def get_llm_council() -> list["LlmClient"]:
    """Return all configured LLM providers for consensus scoring/review."""
    providers: list[LlmClient] = []
    if settings.anthropic_api_key:
        providers.append(LlmClient(api_key=settings.anthropic_api_key))
    if settings.openai_codex:
        providers.append(LlmClient(provider="openai-codex"))
    if settings.google_api_key:
        providers.append(LlmClient(provider="gemini"))
    if not providers:
        providers.append(LlmClient())
    return providers


class LlmClient:
    """LLM client: Anthropic API, Claude Agent SDK, OpenAI Codex SDK, or Gemini."""

    def __init__(self, api_key: str = "", model: str = "", provider: str = "") -> None:
        if provider == "gemini":
            self._backend = "gemini"
            self._google_key = api_key or settings.google_api_key
            self._model = model or settings.gemini_model
        elif provider == "openai-codex":
            self._backend = "openai-codex"
            self._model = model or settings.openai_model
        elif api_key or settings.anthropic_api_key:
            self._backend = "anthropic"
            self._api_key = api_key or settings.anthropic_api_key
            self._model = model or settings.llm_model
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        else:
            self._backend = "claude-sdk"
            self._model = model or settings.llm_model

        self._usage: list[TokenUsage] = []
        self._call_log: list[dict] = []

    def drain_usage(self) -> list[TokenUsage]:
        """Return accumulated token usage and reset."""
        items = self._usage
        self._usage = []
        return items

    def drain_call_log(self) -> list[dict]:
        """Return accumulated call log entries and reset."""
        items = self._call_log
        self._call_log = []
        return items

    def _log_call(self, event: str, detail: str) -> None:
        self._call_log.append({
            "event": event, "detail": detail, "backend": self._backend,
        })

    def _record_usage(self, input_tokens: int, output_tokens: int) -> None:
        prices = MODEL_PRICING.get(self._model, (0, 0))
        cost = (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=round(cost, 6),
            provider=self._backend,
            model=self._model,
        )
        self._usage.append(usage)
        self._log_call(
            "llm_done",
            f"{self._backend}: {input_tokens} in / {output_tokens} out",
        )
        log.info("LLM usage: %d in / %d out (%s)", input_tokens, output_tokens, self._backend)

    async def generate_text(self, prompt: str, max_tokens: int = 4096) -> str:
        """Generate free-form text."""
        try:
            if self._backend == "gemini":
                return await self._generate_via_gemini(prompt, max_tokens)
            if self._backend == "openai-codex":
                return await self._generate_via_codex(prompt)
            if self._backend == "claude-sdk":
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
            self._log_call("llm_start", f"Calling {self._backend} ({self._model})")
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            if hasattr(response, "usage") and response.usage:
                self._record_usage(
                    response.usage.input_tokens, response.usage.output_tokens,
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
            self._log_call("llm_start", f"Calling {self._backend} ({self._model})")
            options = ClaudeAgentOptions(
                disallowed_tools=[
                    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
                    "WebFetch", "WebSearch", "NotebookEdit", "Agent",
                ],
                max_turns=50,
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
            # Agent SDK doesn't expose token counts; estimate from text lengths
            self._record_usage(len(prompt) // 4, len(final) // 4)
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

    async def _generate_via_codex(self, prompt: str) -> str:
        """Generate text via OpenAI Codex SDK (uses ChatGPT subscription)."""
        from openai_codex_sdk import Codex

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        async def _call() -> str:
            self._log_call("llm_start", f"Calling {self._backend} ({self._model})")
            codex = Codex()
            thread = codex.start_thread()
            turn = await thread.run(prompt)
            result = turn.final_response or ""
            self._record_usage(turn.usage.input_tokens, turn.usage.output_tokens)
            if not result:
                raise LlmError("Empty response from Codex SDK")
            log.info("Codex SDK response: result_len=%d", len(result))
            return result

        return await _call()

    async def _generate_via_gemini(self, prompt: str, max_tokens: int) -> str:
        """Generate text via Google Gemini API."""
        from google import genai
        from google.genai import types

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        async def _call() -> str:
            self._log_call("llm_start", f"Calling {self._backend} ({self._model})")
            client = genai.Client(api_key=self._google_key)
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            if not response.text:
                raise LlmError("Empty response from Gemini")
            meta = getattr(response, "usage_metadata", None)
            if meta:
                self._record_usage(
                    getattr(meta, "prompt_token_count", 0),
                    getattr(meta, "candidates_token_count", 0),
                )
            return response.text

        return await _call()

    async def _generate_structured_via_gemini(
        self, prompt: str, schema: type[T], max_tokens: int
    ) -> T:
        """Generate structured output via Gemini's native JSON schema enforcement."""
        from google import genai
        from google.genai import types

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )
        async def _call() -> T:
            self._log_call("llm_start", f"Calling {self._backend} ({self._model})")
            client = genai.Client(api_key=self._google_key)
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    response_mime_type="application/json",
                    response_json_schema=schema.model_json_schema(),
                ),
            )
            if not response.text:
                raise LlmError("Empty structured response from Gemini")
            meta = getattr(response, "usage_metadata", None)
            if meta:
                self._record_usage(
                    getattr(meta, "prompt_token_count", 0),
                    getattr(meta, "candidates_token_count", 0),
                )
            return schema.model_validate_json(response.text)

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
                    self._log_call("cache_hit", f"Cache HIT for {schema.__name__}")
                    return schema.model_validate_json(cached)
                except ValidationError:
                    log.warning("Stale cache entry for schema=%s, regenerating", schema.__name__)
                    await cache.invalidate(ck)

        # Gemini uses native structured output — no JSON extraction needed
        if self._backend == "gemini":
            result = await self._generate_structured_via_gemini(prompt, schema, max_tokens)
            if use_cache:
                await cache.set(ck, result.model_dump_json(), ttl=3600)
            return result

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
