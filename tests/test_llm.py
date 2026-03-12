from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

from app.config import settings
from app.llm import LlmClient, get_secondary_llm


class _FakeSchema(BaseModel):
    name: str
    value: int


class TestProviderSelection:
    def test_gemini_provider(self):
        client = LlmClient(provider="gemini", api_key="fake-key")
        assert client._backend == "gemini"

    @patch("app.llm.settings", MagicMock(
        anthropic_api_key="sk-test", llm_model="claude-sonnet-4-6",
    ))
    @patch("app.llm.AsyncAnthropic", create=True)
    def test_anthropic_provider(self, _mock_anthropic):
        client = LlmClient(api_key="sk-test")
        assert client._backend == "anthropic"

    @patch("app.llm.settings", MagicMock(anthropic_api_key="", llm_model="claude-sonnet-4-6"))
    def test_sdk_fallback(self):
        client = LlmClient()
        assert client._backend == "claude-sdk"


class TestGetSecondaryLlm:
    @patch.object(settings, "google_api_key", "test-key")
    def test_returns_gemini_when_key_set(self):
        result = get_secondary_llm()
        assert result is not None
        assert result._backend == "gemini"

    @patch.object(settings, "google_api_key", "")
    def test_returns_none_when_no_key(self):
        result = get_secondary_llm()
        assert result is None


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
