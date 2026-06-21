import asyncio
import json
import logging
import re
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.article.models import TokenUsage
from app.cache import cache, cache_key
from app.config import settings
from app.errors import LlmError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MODEL_PRICING: dict[str, tuple[float, float]] = {

    "openrouter/deepseek/deepseek-chat": (0.20, 0.80),
}

_LLM_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)

_LLM_CACHE_TTL = 3600

# SDK options shared between text + structured paths
_SDK_DISALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebFetch", "WebSearch", "NotebookEdit", "Agent",
]


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    for i, ch in enumerate(text):
        if ch in "{[":
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
    """Return configured LLM providers for consensus scoring/review.
    Currently returns a single LiteLLM client.
    """
    return [LlmClient()]


class LlmClient:
    """LLM client for LiteLLM (OpenAI-compatible)."""

    def __init__(self, api_key: str = "", model: str = "") -> None:
        self.backend = "openai"
        self._api_key = api_key or settings.litellm_api_key
        self._model = model or settings.litellm_model
        
        if not self._api_key:
            log.warning("LITELLM_API_KEY is not set.")
            
        from openai import AsyncOpenAI
        # Override the SDK User-Agent: some gateways (e.g. Cloudflare-fronted
        # LiteLLM) block the default "OpenAI/Python" UA with a 403.
        self._openai_client = AsyncOpenAI(
            api_key=self._api_key or "dummy",
            base_url=settings.litellm_base_url or None,
            default_headers={"User-Agent": "autoseo/1.0"},
        )

        self._usage: list[TokenUsage] = []
        self._call_log: list[dict] = []

    def _require_client(self, client: Any, name: str) -> Any:
        """Raise LlmError if the backend client is not initialized."""
        if client is None:
            raise LlmError(f"{name} client not initialized (backend={self.backend})")
        return client

    @property
    def model_name(self) -> str:
        """Public read-only access to the model identifier."""
        return self._model

    # --- Usage tracking ---

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
            "event": event, "detail": detail, "backend": self.backend,
        })

    def _record_usage(self, input_tokens: int, output_tokens: int) -> None:
        prices = MODEL_PRICING.get(self._model, (0, 0))
        if prices == (0, 0) and self._model:
            log.warning("No pricing for model %s — cost will show $0", self._model)
        cost = (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=round(cost, 6),
            provider=self.backend,
            model=self._model,
        )
        self._usage.append(usage)
        self._log_call(
            "llm_done",
            f"{self.backend}: {input_tokens} in / {output_tokens} out",
        )
        log.info("LLM usage: %d in / %d out (%s)", input_tokens, output_tokens, self.backend)

    def _record_sdk_usage(self, message: Any) -> None:
        """Extract real usage from Agent SDK ResultMessage."""
        sdk_usage = message.usage or {}
        in_tok = (
            sdk_usage.get("input_tokens", 0)
            + sdk_usage.get("cache_creation_input_tokens", 0)
            + sdk_usage.get("cache_read_input_tokens", 0)
        )
        out_tok = sdk_usage.get("output_tokens", 0)
        self._record_usage(in_tok, out_tok)
        if message.total_cost_usd is not None and self._usage:
            self._usage[-1].cost = round(message.total_cost_usd, 6)

    def _record_gemini_usage(self, response: Any) -> None:
        """Extract usage from Gemini response metadata."""
        meta = getattr(response, "usage_metadata", None)
        if meta:
            self._record_usage(
                getattr(meta, "prompt_token_count", 0),
                getattr(meta, "candidates_token_count", 0),
            )

    def _record_codex_usage(self, turn: Any) -> None:
        """Extract usage from Codex turn."""
        if turn.usage:
            in_tok = (
                getattr(turn.usage, "input_tokens", 0)
                + getattr(turn.usage, "cached_input_tokens", 0)
            )
            self._record_usage(in_tok, getattr(turn.usage, "output_tokens", 0))

    def _sdk_options(self, **overrides: Any) -> Any:
        """Build ClaudeAgentOptions with shared defaults."""
        from claude_agent_sdk import ClaudeAgentOptions

        defaults: dict[str, Any] = {
            "disallowed_tools": _SDK_DISALLOWED_TOOLS,
            "max_turns": 50,
            "max_budget_usd": 1.00,
            "model": self._model,
            "system_prompt": (
                "You are a direct text generator. "
                "Respond only with the requested content."
            ),
        }
        defaults.update(overrides)
        return ClaudeAgentOptions(**defaults)  # type: ignore[arg-type]

    # --- SDK sync runners (called via asyncio.to_thread) ---

    @staticmethod
    def _run_sdk_sync(prompt: str, options: Any) -> dict[str, Any]:
        """Run Agent SDK query synchronously — designed to run in a thread."""
        import asyncio as _aio

        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query

        async def _inner() -> dict[str, Any]:
            result_text = ""
            assistant_text = ""
            usage_msg = None
            error = ""
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            assistant_text += block.text
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        error = message.result or "Unknown SDK error"
                    else:
                        result_text = message.result or ""
                    usage_msg = message
            return {
                "text": result_text or assistant_text,
                "usage": usage_msg,
                "error": error,
            }

        return _aio.run(_inner())

    @staticmethod
    def _run_sdk_structured_sync(prompt: str, options: Any) -> dict[str, Any]:
        """Run Agent SDK structured query synchronously — designed to run in a thread."""
        import asyncio as _aio

        from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock, query

        async def _inner() -> dict[str, Any]:
            structured_data = None
            usage_msg = None
            error = ""
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock) and block.name == "StructuredOutput":
                            structured_data = block.input
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        error = message.result or "Unknown SDK error"
                    usage_msg = message
            return {"data": structured_data, "usage": usage_msg, "error": error}

        return _aio.run(_inner())

    # --- Text generation ---

    async def generate_text(self, prompt: str, max_tokens: int = 4096) -> str:
        """Generate free-form text using LiteLLM."""
        client = self._require_client(self._openai_client, "OpenAI")

        @_LLM_RETRY
        async def _call() -> str:
            self._log_call("llm_start", f"Calling {self.backend} ({self._model})")
            response = await client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            if response.usage:
                self._record_usage(
                    response.usage.prompt_tokens, response.usage.completion_tokens,
                )
            content = response.choices[0].message.content
            if not content:
                raise LlmError("Empty response from OpenAI")
            return content

        return await _call()

    # --- Structured output (native via LiteLLM) ---

    async def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        max_tokens: int = 4096,
        use_cache: bool = True,
    ) -> T:
        """Generate structured output parsed into a Pydantic model using LiteLLM JSON mode."""
        ck = cache_key("llm", prompt, self._model, schema.__name__)

        if use_cache:
            cached = await cache.get(ck)
            if cached:
                try:
                    log.info("LLM cache hit for schema=%s", schema.__name__)
                    self._log_call("cache_hit", f"Cache HIT for {schema.__name__}")
                    return schema.model_validate_json(cached)
                except ValidationError:
                    log.warning("Stale cache for schema=%s", schema.__name__)
                    await cache.invalidate(ck)

        client = self._require_client(self._openai_client, "OpenAI")

        @_LLM_RETRY
        async def _call() -> T:
            self._log_call("llm_start", f"Calling {self.backend} ({self._model})")
            import json
            schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"))
            full_prompt = (
                f"{prompt}\n\n"
                f"Respond ONLY with valid JSON matching this schema:\n{schema_json}"
            )
            response = await client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": full_prompt}],
            )
            if response.usage:
                self._record_usage(
                    response.usage.prompt_tokens, response.usage.completion_tokens,
                )
            content = response.choices[0].message.content or ""
            if not content:
                raise LlmError("Empty structured response from OpenAI")
            json_str = _extract_json(content)
            return schema.model_validate_json(json_str)

        try:
            result = await _call()
        except LlmError:
            raise
        except Exception as e:
            raise LlmError(f"Structured output failed: {e}") from e

        if use_cache:
            await cache.set(ck, result.model_dump_json(), ttl=_LLM_CACHE_TTL)
        return result

    # --- Tool use ---

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict],
        tool_handler: Callable,
        schema: type[T],
        max_tool_rounds: int = 5,
    ) -> T:
        """Generate structured output with tool use via OpenAI format."""
        client = self._require_client(self._openai_client, "OpenAI")
        import json
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system = (
            f"You have research tools available. Use them to gather data, "
            f"then respond with JSON matching this schema:\n{schema_json}"
        )
        messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        
        openai_tools = [{"type": "function", "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        }} for t in tools]

        for round_num in range(max_tool_rounds):
            self._log_call("llm_start", f"Tool round {round_num + 1}")
            try:
                response = await client.chat.completions.create(
                    model=self._model,
                    max_tokens=4096,
                    messages=messages,
                    tools=openai_tools,
                )
            except Exception as e:
                raise LlmError(f"Tool calling failed: {e}") from e

            if response.usage:
                self._record_usage(response.usage.prompt_tokens, response.usage.completion_tokens)

            msg = response.choices[0].message
            if not msg.tool_calls:
                json_str = _extract_json(msg.content or "")
                return schema.model_validate_json(json_str)

            messages.append(msg.model_dump(exclude_none=True))
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                result_str = await tool_handler(tc.function.name, args)
                self._log_call("tool_use", f"{tc.function.name}(...)")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        raise LlmError(f"OpenAI tool use exceeded {max_tool_rounds} rounds")
