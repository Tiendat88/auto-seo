"""Tests for query fan-out: prompt, parsing, gap analysis."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.aeo.fanout import (
    _build_fanout_prompt,
    _build_gap_summary,
    _chunk_sentences,
    _embed_texts,
    analyze_gaps,
)
from app.aeo.models import (
    LlmFanOutResult,
    LlmSubQuery,
    SubQuery,
    SubQueryType,
)
from app.config import settings
from app.errors import LlmError

# --- Prompt ---


class TestFanOutPrompt:
    def test_prompt_includes_query(self):
        prompt = _build_fanout_prompt("best AI writing tool")
        assert "best AI writing tool" in prompt

    def test_prompt_includes_all_types(self):
        prompt = _build_fanout_prompt("test query")
        for t in SubQueryType:
            assert t.value in prompt

    def test_prompt_includes_json_example(self):
        prompt = _build_fanout_prompt("test query")
        assert '"sub_queries"' in prompt
        assert '"type"' in prompt
        assert '"query"' in prompt


# --- Parsing (via Pydantic model) ---


class TestFanOutParsing:
    def test_valid_result(self):
        result = LlmFanOutResult(sub_queries=[
            LlmSubQuery(type=SubQueryType.COMPARATIVE, query="A vs B"),
            LlmSubQuery(type=SubQueryType.HOW_TO, query="how to do X"),
        ])
        assert len(result.sub_queries) == 2
        assert result.sub_queries[0].type == SubQueryType.COMPARATIVE

    def test_all_types_valid(self):
        sqs = [
            LlmSubQuery(type=SubQueryType(t.value), query=f"query for {t.value}")
            for t in SubQueryType
        ]
        result = LlmFanOutResult(sub_queries=sqs)
        assert len(result.sub_queries) == 6

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError):
            LlmSubQuery(type="invalid_type", query="test")

    def test_empty_query_accepted(self):
        # Pydantic doesn't enforce min_length on LlmSubQuery.query
        sq = LlmSubQuery(type=SubQueryType.COMPARATIVE, query="")
        assert sq.query == ""


# --- Sentence Chunking ---


class TestChunking:
    def test_splits_sentences(self):
        text = (
            "This is the first complete sentence with enough words. "
            "Here is another sentence that also has enough words. "
            "And a third sentence to make this a proper paragraph."
        )
        chunks = _chunk_sentences(text)
        assert len(chunks) >= 2

    def test_filters_short_fragments(self):
        text = "OK. Fine. This is a proper sentence with enough words."
        chunks = _chunk_sentences(text)
        assert all(len(c.split()) >= 5 for c in chunks)


# --- Gap Analysis ---


class TestGapAnalysis:
    def test_covered_content(self):
        """Content that closely matches a sub-query should be marked covered."""
        sub_queries = [
            SubQuery(
                type=SubQueryType.DEFINITIONAL,
                query="what is retrieval augmented generation",
            ),
        ]
        content = (
            "Retrieval augmented generation is a technique that combines a large language "
            "model with an external knowledge base. The model retrieves relevant documents "
            "at inference time and uses them to produce grounded factual answers."
        )
        with patch(
            "app.aeo.fanout._embed_texts",
            side_effect=[
                [[0.99, 0.01], [0.98, 0.02]],
                [[1.0, 0.0]],
            ],
        ):
            updated, _ = analyze_gaps(sub_queries, content)
        assert updated[0].similarity_score is not None
        assert updated[0].similarity_score > 0.5

    def test_uncovered_content(self):
        """Unrelated content should produce low similarity."""
        sub_queries = [
            SubQuery(
                type=SubQueryType.TRUST_SIGNALS,
                query="customer reviews for CRM software 2025",
            ),
        ]
        content = (
            "Chocolate cake is a popular dessert. Mix flour, sugar, cocoa powder, "
            "and eggs together. Bake at 350 degrees for 30 minutes."
        )
        with patch(
            "app.aeo.fanout._embed_texts",
            side_effect=[
                [[0.0, 1.0], [0.1, 0.9]],
                [[1.0, 0.0]],
            ],
        ):
            updated, _ = analyze_gaps(sub_queries, content)
        assert updated[0].similarity_score is not None
        assert updated[0].similarity_score < 0.72
        assert not updated[0].covered

    def test_empty_content(self):
        sub_queries = [
            SubQuery(type=SubQueryType.HOW_TO, query="how to use a CRM"),
        ]
        updated, _ = analyze_gaps(sub_queries, "")
        assert not updated[0].covered
        assert updated[0].similarity_score == 0.0

    def test_gap_summary_counts(self):
        sub_queries = [
            SubQuery(type=SubQueryType.COMPARATIVE, query="a", covered=True, similarity_score=0.8),
            SubQuery(type=SubQueryType.COMPARATIVE, query="b", covered=True, similarity_score=0.75),
            SubQuery(type=SubQueryType.HOW_TO, query="c", covered=False, similarity_score=0.3),
        ]
        summary = _build_gap_summary(sub_queries)
        assert summary.covered == 2
        assert summary.total == 3
        assert summary.coverage_percent == 67
        assert "comparative" in summary.covered_types
        assert "how_to" in summary.missing_types

    def test_embed_texts_uses_voyage_model_and_batches(self):
        mock_client = MagicMock()
        mock_client.embed.side_effect = [
            MagicMock(embeddings=[[1.0, 0.0]] * 128),
            MagicMock(embeddings=[[0.0, 1.0], [0.5, 0.5]]),
        ]

        texts = [f"sentence {i}" for i in range(130)]
        with (
            patch("app.aeo.fanout._get_embedding_client", return_value=mock_client),
            patch.object(settings, "voyage_embedding_model", "voyage-4-large"),
        ):
            embeddings = _embed_texts(texts, input_type="document")

        assert len(embeddings) == 130
        assert mock_client.embed.call_count == 2
        first_call = mock_client.embed.call_args_list[0].kwargs
        assert first_call["model"] == "voyage-4-large"
        assert first_call["input_type"] == "document"
        assert first_call["truncation"] is True

    def test_embed_texts_requires_configured_api_key(self):
        with (
            patch("app.aeo.fanout._voyage_client", None),
            patch.object(settings, "voyage_api_key", ""),
        ):
            with pytest.raises(LlmError, match="VOYAGE_API_KEY"):
                _embed_texts(["hello"], input_type="query")


# --- Fan-Out Integration (mocked LLM) ---


class TestFanOutGeneration:
    @pytest.mark.asyncio
    async def test_generate_sub_queries_success(self):
        from app.aeo.fanout import generate_sub_queries

        mock_result = LlmFanOutResult(sub_queries=[
            LlmSubQuery(type=SubQueryType.COMPARATIVE, query="A vs B"),
            LlmSubQuery(type=SubQueryType.COMPARATIVE, query="C vs D"),
            LlmSubQuery(type=SubQueryType.FEATURE_SPECIFIC, query="feature X"),
            LlmSubQuery(type=SubQueryType.FEATURE_SPECIFIC, query="feature Y"),
            LlmSubQuery(type=SubQueryType.USE_CASE, query="use case 1"),
            LlmSubQuery(type=SubQueryType.USE_CASE, query="use case 2"),
            LlmSubQuery(type=SubQueryType.TRUST_SIGNALS, query="review 1"),
            LlmSubQuery(type=SubQueryType.TRUST_SIGNALS, query="review 2"),
            LlmSubQuery(type=SubQueryType.HOW_TO, query="how to 1"),
            LlmSubQuery(type=SubQueryType.HOW_TO, query="how to 2"),
            LlmSubQuery(type=SubQueryType.DEFINITIONAL, query="what is X"),
            LlmSubQuery(type=SubQueryType.DEFINITIONAL, query="what is Y"),
        ])

        mock_llm = MagicMock()
        mock_llm.generate_structured = AsyncMock(return_value=mock_result)
        mock_llm.model_name = "test-model"

        sub_queries, model = await generate_sub_queries("test query", mock_llm)
        assert len(sub_queries) == 12
        assert model == "test-model"
        types = {sq.type for sq in sub_queries}
        assert len(types) == 6

    @pytest.mark.asyncio
    async def test_generate_sub_queries_llm_failure(self):
        from app.aeo.fanout import generate_sub_queries
        from app.errors import LlmError

        mock_llm = MagicMock()
        mock_llm.model_name = "test-model"
        mock_llm.generate_structured = AsyncMock(side_effect=LlmError("API down"))

        with pytest.raises(LlmError):
            await generate_sub_queries("test query", mock_llm)
