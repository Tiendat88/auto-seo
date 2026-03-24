"""Query fan-out engine: LLM sub-query generation + semantic gap analysis."""

import logging

from sentence_transformers import SentenceTransformer, util

from app.aeo.models import (
    GapSummary,
    LlmFanOutResult,
    SubQuery,
    SubQueryType,
)
from app.article.constants import SENTENCE_END_RE
from app.config import settings
from app.llm import LlmClient

log = logging.getLogger(__name__)

_model: SentenceTransformer | None = None

_REQUIRED_TYPES = {t.value for t in SubQueryType}


def _get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# --- Prompt ---


def _build_fanout_prompt(query: str) -> str:
    return f"""You are a search query decomposition engine. Given a user's target query, \
generate 10-15 sub-queries that simulate how AI search engines (ChatGPT, Perplexity, \
Gemini) decompose a query to build a comprehensive answer.

Target query: "{query}"

Each sub-query must belong to exactly one of these 6 types:

1. comparative — Query vs. alternatives or competitors
2. feature_specific — Specific capability, feature, or attribute focus
3. use_case — Real-world application or scenario
4. trust_signals — Reviews, case studies, credibility, proof points
5. how_to — Procedural, instructional, step-by-step
6. definitional — Conceptual, "what is", foundational knowledge

Requirements:
- Generate between 10 and 15 sub-queries total
- Include at least 2 sub-queries for EACH of the 6 types
- Sub-queries should be realistic search queries a user might type
- Vary the specificity — mix broad and narrow queries

Return ONLY a valid JSON object with this exact schema (no markdown, no explanation):

{{
  "sub_queries": [
    {{"type": "<type>", "query": "<sub-query text>"}},
    ...
  ]
}}

Example for the query "best CRM for startups":

{{
  "sub_queries": [
    {{"type": "comparative", "query": "HubSpot vs Salesforce vs Pipedrive for startups"}},
    {{"type": "comparative", "query": "free CRM vs paid CRM for small business"}},
    {{"type": "feature_specific", "query": "CRM with built-in email automation for startups"}},
    {{"type": "feature_specific", "query": "CRM with pipeline management and forecasting"}},
    {{"type": "use_case", "query": "CRM for SaaS startup sales team of 5"}},
    {{"type": "use_case", "query": "CRM for managing investor and partner relationships"}},
    {{"type": "trust_signals", "query": "CRM reviews from Y Combinator startups 2025"}},
    {{"type": "trust_signals", "query": "CRM customer retention case study small business"}},
    {{"type": "how_to", "query": "how to set up a CRM pipeline for B2B startup"}},
    {{"type": "how_to", "query": "how to migrate from spreadsheets to a CRM"}},
    {{"type": "definitional", "query": "what is a CRM and why do startups need one"}},
    {{"type": "definitional", "query": "CRM vs spreadsheet for contact management"}}
  ]
}}

Do not add any fields beyond "type" and "query". Do not include markdown fences or any \
text outside the JSON object."""


# --- Sub-query generation ---


async def generate_sub_queries(query: str, llm: LlmClient) -> tuple[list[SubQuery], str]:
    """Generate sub-queries via LLM. Returns (sub_queries, model_used)."""
    from app.aeo.store import get_cached_fanout, set_cached_fanout

    # Check Redis cache
    cached = await get_cached_fanout(query, llm.model_name)
    if cached:
        log.info("Cache hit for fanout: %s (model=%s)", query, llm.model_name)
        result = LlmFanOutResult.model_validate(cached)
    else:
        prompt = _build_fanout_prompt(query)
        result = await llm.generate_structured(prompt, LlmFanOutResult)
        await set_cached_fanout(query, llm.model_name, result.model_dump(mode="json"))

    sub_queries = [SubQuery(type=sq.type, query=sq.query) for sq in result.sub_queries]

    # Log coverage of types
    types_present = {sq.type.value for sq in sub_queries}
    missing = _REQUIRED_TYPES - types_present
    if missing:
        log.warning("Fan-out missing types: %s", missing)

    return sub_queries, llm.model_name


# --- Gap analysis ---


def _chunk_sentences(text: str) -> list[str]:
    """Split text into sentences, filtering short fragments."""
    raw = SENTENCE_END_RE.split(text)
    return [s.strip() for s in raw if s.strip() and len(s.strip().split()) >= 5]


def analyze_gaps(
    sub_queries: list[SubQuery], content: str,
) -> tuple[list[SubQuery], GapSummary]:
    """Check content coverage for each sub-query using sentence embeddings."""
    threshold = settings.aeo_similarity_threshold
    model = _get_embedding_model()

    sentences = _chunk_sentences(content)
    if not sentences:
        # No usable content — everything is a gap
        updated = [
            SubQuery(type=sq.type, query=sq.query, covered=False, similarity_score=0.0)
            for sq in sub_queries
        ]
        return updated, _build_gap_summary(updated)

    query_texts = [sq.query for sq in sub_queries]
    content_embeddings = model.encode(sentences, convert_to_tensor=True)
    query_embeddings = model.encode(query_texts, convert_to_tensor=True)

    similarities = util.cos_sim(query_embeddings, content_embeddings)

    updated: list[SubQuery] = []
    for i, sq in enumerate(sub_queries):
        max_sim = float(similarities[i].max().item())
        updated.append(SubQuery(
            type=sq.type,
            query=sq.query,
            covered=max_sim >= threshold,
            similarity_score=round(max_sim, 2),
        ))

    return updated, _build_gap_summary(updated)


def _build_gap_summary(sub_queries: list[SubQuery]) -> GapSummary:
    covered_count = sum(1 for sq in sub_queries if sq.covered)
    total = len(sub_queries)

    covered_types: set[str] = set()
    all_types: set[str] = set()
    for sq in sub_queries:
        all_types.add(sq.type.value)
        if sq.covered:
            covered_types.add(sq.type.value)
    missing_types = sorted(all_types - covered_types)

    return GapSummary(
        covered=covered_count,
        total=total,
        coverage_percent=round(covered_count / total * 100) if total else 0,
        covered_types=sorted(covered_types),
        missing_types=missing_types,
    )
