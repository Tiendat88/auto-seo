from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

from app.config import settings
from app.llm import LlmClient, get_llm_council


class _FakeSchema(BaseModel):
    name: str
    value: int


class TestProviderSelection:
    def test_gemini_provider(self):
        client = LlmClient(provider="gemini", api_key="fake-key")
        assert client.backend == "gemini"

    @patch("app.llm.settings", MagicMock(
        anthropic_api_key="sk-test", llm_model="claude-sonnet-4-6", openai_codex=False,
    ))
    @patch("app.llm.AsyncAnthropic", create=True)
    def test_anthropic_provider(self, _mock_anthropic):
        client = LlmClient(api_key="sk-test")
        assert client.backend == "anthropic"

    @patch("app.llm.settings", MagicMock(
        anthropic_api_key="", llm_model="claude-sonnet-4-6", openai_codex=False, google_api_key="",
    ))
    def test_sdk_fallback(self):
        client = LlmClient()
        assert client.backend == "claude-sdk"

    @patch("app.llm.settings", MagicMock(
        anthropic_api_key="",
        llm_model="claude-sonnet-4-6",
        openai_codex=False,
        google_api_key="gk-test",
        gemini_model="gemini-3-flash-preview",
    ))
    @patch("google.genai.Client")
    def test_default_prefers_gemini_when_google_key_available(self, mock_genai_client_cls):
        client = LlmClient()
        assert client.backend == "gemini"
        assert client._model == "gemini-3-flash-preview"
        mock_genai_client_cls.assert_called_once_with(api_key="gk-test")

    def test_codex_provider(self):
        client = LlmClient(provider="openai-codex")
        assert client.backend == "openai-codex"

    @patch("app.llm.settings", MagicMock(openai_model="o3-mini"))
    def test_codex_with_model(self):
        client = LlmClient(provider="openai-codex")
        assert client.backend == "openai-codex"
        assert client._model == "o3-mini"


class TestGetLlmCouncil:
    @patch.object(settings, "anthropic_api_key", "sk-test")
    @patch.object(settings, "google_api_key", "gk-test")
    @patch.object(settings, "openai_codex", True)
    @patch.object(settings, "openai_model", "o3-mini")
    def test_returns_all_configured(self):
        council = get_llm_council()
        backends = [c.backend for c in council]
        assert "anthropic" in backends
        assert "gemini" in backends
        assert "openai-codex" in backends
        assert len(council) == 3

    @patch.object(settings, "anthropic_api_key", "")
    @patch.object(settings, "google_api_key", "")
    @patch.object(settings, "openai_codex", False)
    def test_fallback_to_claude_sdk(self):
        council = get_llm_council()
        assert len(council) == 1
        assert council[0].backend == "claude-sdk"

    @patch.object(settings, "anthropic_api_key", "")
    @patch.object(settings, "google_api_key", "gk-test")
    @patch.object(settings, "openai_codex", False)
    def test_single_provider(self):
        council = get_llm_council()
        assert len(council) == 1
        assert council[0].backend == "gemini"


class TestGeminiBackend:
    @patch("google.genai.Client")
    async def test_generate_text_routes_to_gemini(self, mock_genai_client_cls):
        mock_response = MagicMock()
        mock_response.text = "Hello world"

        mock_aio = MagicMock()
        mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

        mock_instance = MagicMock()
        mock_instance.aio = mock_aio
        mock_genai_client_cls.return_value = mock_instance

        client = LlmClient(provider="gemini", api_key="test-key")
        result = await client.generate_text("test prompt")

        assert result == "Hello world"
        mock_aio.models.generate_content.assert_awaited_once()

    @patch("google.genai.Client")
    async def test_generate_structured_uses_native_json(self, mock_genai_client_cls):
        mock_response = MagicMock()
        mock_response.text = '{"name": "test", "value": 42}'

        mock_aio = MagicMock()
        mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

        mock_instance = MagicMock()
        mock_instance.aio = mock_aio
        mock_genai_client_cls.return_value = mock_instance

        client = LlmClient(provider="gemini", api_key="test-key")

        with patch("app.llm.cache") as mock_cache:
            mock_cache.get = AsyncMock(return_value=None)
            mock_cache.set = AsyncMock()
            result = await client.generate_structured("test prompt", _FakeSchema)

        assert isinstance(result, _FakeSchema)
        assert result.name == "test"
        assert result.value == 42
        mock_aio.models.generate_content.assert_awaited_once()
