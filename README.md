# SEO Article Generator

Backend service that generates SEO-optimized articles using an agent-based pipeline. Takes a topic, analyzes the competitive SERP landscape, and produces a publish-ready article with SEO metadata, keyword analysis, linking suggestions, quality scoring, JSON-LD schema markup, and content humanization.

## Quick Start

```bash
# 1. Start PostgreSQL and Redis
docker-compose up -d

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY (and optionally GOOGLE_API_KEY)

# 4. Start the server
uvicorn app.main:app --reload

# 5. Generate an article
autoseo generate "best productivity tools for remote teams"
```

## Architecture

```
POST /jobs → Job(PENDING) → Background pipeline:
  RESEARCHING → ANALYZING → OUTLINING → GENERATING → SCORING → REVIEWING → COMPLETED
                                                         ↑                      │
                                                         └── edit loop (max 2) ─┘
```

**Linear state machine pipeline** — each step saves intermediate results to the database as JSON. If the process crashes, jobs resume from the last completed step.

### Pipeline Steps

1. **Research** — Fetch top 10 SERP results for the topic (mock or real SerpAPI)
2. **Analyze** — LLM extracts themes, keywords, content gaps, and search intent from SERP data
3. **Outline** — LLM generates a structured outline with editorial brief (audience, tone, angle, differentiators), word count budgets per section, and optional brand voice alignment
4. **Generate** — Single LLM call produces the full article with FAQ, parsed from markdown. Three parallel calls generate SEO metadata, link suggestions, and 5 meta tag options. Content is post-processed by the scrubber (AI filler removal, zero-width Unicode stripping, paragraph splitting)
5. **Score** — Hybrid quality scoring: 6 algorithmic checks (keyword usage, heading structure, word count, readability, humanity, keyword distribution) + 6 LLM-evaluated dimensions (content depth, differentiation, accuracy, consistency, readability, actionability) = 12 total
6. **Review** — Holistic LLM editorial review across 7 quality categories with issue-level feedback
7. **Edit** *(conditional)* — If score or review fails, the article is edited in place using feedback, scrubbed again, then re-scored and re-reviewed (capped at `MAX_REVISIONS`)

### Multi-Provider Scoring

When `GOOGLE_API_KEY` is configured, scoring and review run on **both Claude and Gemini** in parallel:
- **Scoring**: 6 LLM calls (3 Claude + 3 Gemini). Dimensions with the same name are averaged; feedback from the lower-scoring provider is kept
- **Review**: 2 calls (Claude + Gemini). Issues from both providers are collected; `passed = true` only if no critical/major issues exist across both

Falls back to single-provider (Claude only) when `GOOGLE_API_KEY` is not set.

### Tech Stack

| Component | Choice |
|-----------|--------|
| API | FastAPI |
| Database | PostgreSQL + async SQLAlchemy |
| LLM | Anthropic Claude (API or Agent SDK) + Google Gemini |
| SERP | Mock provider (default) / SerpAPI |
| Cache | Redis |
| CLI | Typer + Rich |
| Readability | textstat (Flesch RE, grade level) |

## API Endpoints

```
POST /api/jobs/              Create article generation job
GET  /api/jobs/              List jobs (filter by status, paginated)
GET  /api/jobs/{id}          Get job status and result
POST /api/jobs/{id}/resume   Resume a failed job
GET  /health                 Health check
```

### Create a job

```bash
curl -X POST http://localhost:8000/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{"topic": "best productivity tools for remote teams", "target_word_count": 1500, "language": "en"}'
```

Optional fields: `brand_voice` (object with `brand_name`, `voice_description`, `writing_examples`, `style_notes`).

### Check status

```bash
curl http://localhost:8000/api/jobs/{job_id}
```

## CLI Client

```bash
autoseo                                              # Show help
autoseo generate "best productivity tools" --words 1500
autoseo generate "topic" --brand-voice brand.json   # With brand voice context
autoseo status <job-id>
autoseo watch <job-id>                               # Reconnect to a running job
autoseo result <job-id>                              # Full markdown render
autoseo result <job-id> --summary                    # Compact quality summary
autoseo result <job-id> --json                       # Raw JSON output
autoseo list --status completed
autoseo resume <job-id>                              # Resume failed job (or watch if running)
autoseo export <job-id> article.md                   # Markdown with JSON-LD schema
```

## Output Structure

The completed job returns an `ArticleResult` with:

- **seo_metadata** — title tag (<60 chars), meta description (<160 chars), primary keyword, slug
- **content** — article sections with heading hierarchy (H1/H2/H3), FAQ items, total word count
- **keyword_analysis** — primary/secondary keyword counts, density, placement locations, and section-level keyword distribution with evenness score
- **links** — 3-5 internal link suggestions, 2-4 external reference suggestions
- **quality** — overall score (0-1), 12 per-dimension scores (6 algorithmic + 6 LLM), revision instructions if below threshold
- **review** — pass/fail with issue-level feedback (category, severity, suggestion), strengths list
- **schema_markup** — Article + FAQPage JSON-LD structured data for rich snippets
- **meta_options** — 5 alternative title tags + 5 alternative meta descriptions
- **snippet_opportunities** — detected list, table, definition, and Q&A featured snippet opportunities
- **competitive_analysis** — themes, keywords, content gaps from SERP analysis
- **outline** — structured outline with editorial brief and per-section word budgets

## Testing

```bash
pytest tests/ -v
```

**142 tests** across 8 test files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 48 | Pydantic validation, serialization, constraints, BrandVoice, SeoMetaOptions, KeywordDistribution, SchemaMarkup |
| `test_pipeline.py` | 27 | State machine, resume, markdown parser, edit loop, merge functions, multi-provider scoring/review |
| `test_quality.py` | 17 | Algorithmic scoring: keyword usage, heading structure, word count, readability (Flesch), humanity (AI detection), keyword distribution |
| `test_api.py` | 13 | API endpoints, error handling, CRUD, resume edge cases |
| `test_seo.py` | 12 | SEO constraint validation |
| `test_schema.py` | 9 | JSON-LD schema generation, FAQPage markup, featured snippet detection |
| `test_scrubber.py` | 9 | Content scrubber: zero-width removal, em-dash replacement, filler removal, word substitutions, paragraph splitting |
| `test_llm.py` | 7 | Provider selection, Gemini backend routing, `get_secondary_llm` |

Tests use in-memory SQLite (no PostgreSQL required) and mock LLM/SERP providers.

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key (if set, uses API backend; otherwise falls back to Claude Agent SDK) |
| `GOOGLE_API_KEY` | — | Enables Gemini as secondary provider for scoring and review |
| `LLM_MODEL` | `claude-sonnet-4-6` | Anthropic model to use |
| `GEMINI_MODEL` | `gemini-3-pro-preview` | Gemini model to use |
| `SERP_PROVIDER` | `mock` | `mock` or `serpapi` |
| `SERPAPI_KEY` | — | Required if `SERP_PROVIDER=serpapi` |
| `DATABASE_URL` | `postgresql+asyncpg://seo:seo@localhost:5432/seo_agent` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for caching |
| `QUALITY_THRESHOLD` | `0.7` | Minimum quality score (0-1) to skip edit loop |
| `MAX_REVISIONS` | `2` | Max edit loop iterations on quality/review failure |

## Design Decisions

**State machine over agent framework** — The pipeline is sequential (SERP → analyze → outline → generate → score → review). A clean state machine with DB persistence is simpler, more testable, and easier to debug than LangGraph or similar frameworks.

**Single-call article generation** — The full article (including FAQ) is generated in one LLM call and parsed from markdown. This produces coherent narrative flow and natural transitions between sections, compared to section-by-section generation which leads to repetition and isolation.

**Editorial brief in outline step** — The outline LLM call also generates an editorial brief (audience, tone, angle, differentiators). This embeds strategic context into the outline without adding a separate pipeline step, and propagates to all downstream prompts.

**Hybrid quality scoring** — 6 algorithmic checks (keyword usage, heading structure, word count, readability via Flesch RE, humanity/AI detection, keyword distribution) are deterministic, free, and instant. 6 LLM-based checks (content depth, differentiation, accuracy, consistency, readability, actionability) catch subjective quality issues. Combined 12-dimension score with configurable threshold.

**Content scrubber** — Post-processes articles after generation and editing with moderate aggressiveness: strips zero-width Unicode watermarks, replaces em-dashes, removes AI filler openers, substitutes overused AI words (leverage → use, delve → explore), and splits long paragraphs. Catches what prompts miss.

**Brand voice context** — Optional `BrandVoice` (name, description, writing examples, style notes) is injected into outline, generation, and editing prompts. Produces consistent brand-aligned content without changing the pipeline structure.

**Multi-provider consensus** — When Gemini is configured, scoring and review run on both Claude and Gemini in parallel. Averaging scores reduces single-model bias; collecting issues from both providers catches more problems. Graceful degradation: if one provider fails, the other's results are used alone.

**Edit loop over regeneration** — When quality/review fails, the article is edited in place using specific feedback rather than regenerated from scratch. This preserves what's already good and focuses LLM effort on the weakest areas.

**Resume = re-enter state machine** — Each step's output is persisted to DB before advancing. On crash/failure, `_determine_resume_index()` finds the first missing output and resumes from there. No complex checkpointing needed.

**Redis caching** — SERP results cached 24h, LLM responses cached 1h. Graceful degradation: if Redis is down, caching is silently disabled.

**Mock SERP by default** — The `MockSerpProvider` generates realistic results based on the topic string, so the system works end-to-end without API keys. Swap to real SerpAPI via config.

## Usage Guide

### Generate your first article

```bash
# Start the server (use --workers 2 to prevent Agent SDK from blocking requests)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Generate with live progress tracking
autoseo generate "best project management tools for startups 2026" --words 1500
```

The CLI shows a live progress bar with step-by-step output as the pipeline runs. Each stage (Research, Analyze, Outline, Generate, Score, Review) renders its results inline. Sub-steps like `Generate (article)` and `Score (llm)` show what's happening inside long-running stages.

### Use brand voice

Create a JSON file with your brand's writing style:

```json
{
  "brand_name": "Acme Corp",
  "voice_description": "Professional but approachable, like a knowledgeable colleague",
  "writing_examples": ["We tested 50+ tools so you don't have to."],
  "style_notes": "Use active voice. Short paragraphs. No jargon."
}
```

```bash
autoseo generate "topic" --brand-voice brand.json
```

### Monitor and manage jobs

```bash
# Watch a running job (reconnect after disconnect)
autoseo watch <job-id>

# Resume a failed job from its last checkpoint
autoseo resume <job-id>

# View quality scores and review feedback
autoseo result <job-id> --summary

# Export with JSON-LD schema markup
autoseo export <job-id> article.md
```

### Use the API directly

```bash
# Create a job
curl -X POST http://localhost:8000/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{"topic": "best AI tools 2026", "target_word_count": 1500}'

# Poll status (current_step shows sub-steps like "generating:article")
curl http://localhost:8000/api/jobs/{job_id}

# Resume a failed job
curl -X POST http://localhost:8000/api/jobs/{job_id}/resume
```

### Typical pipeline run

A full run takes 5-15 minutes depending on the LLM backend and edit loop iterations:

| Step | Duration | Details |
|------|----------|---------|
| Research | ~1s | SERP fetch (mock: instant, SerpAPI: 2-3s) |
| Analyze | ~10s | LLM competitive analysis |
| Outline | ~10s | LLM outline + editorial brief |
| Generate | 2-5 min | Article LLM call + 3 parallel metadata calls |
| Score | ~30s | 6 algorithmic + 6 LLM scoring dimensions |
| Review | ~30s | Holistic editorial review (2x with Gemini) |
| Edit loop | 3-8 min | Up to 2 revision cycles if quality/review fails |

### Production deployment

```bash
# Required: PostgreSQL + Redis
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Recommended env vars
ANTHROPIC_API_KEY=sk-...          # Required for LLM calls
GOOGLE_API_KEY=...                # Optional: enables dual-provider scoring
SERP_PROVIDER=serpapi             # Real SERP data
SERPAPI_KEY=...                   # Required with serpapi provider
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
QUALITY_THRESHOLD=0.7             # Min score to skip editing
MAX_REVISIONS=2                   # Edit loop cap
```

> **Note**: Use `--workers 2` with uvicorn. The Claude Agent SDK blocks the event loop during long generation calls (~5 min). Multiple workers ensure the API remains responsive while the pipeline runs.

## Project Structure

```
app/
├── main.py              # FastAPI app, lifespan
├── config.py            # pydantic-settings
├── db.py                # Async SQLAlchemy engine/sessions
├── llm.py               # LlmClient (Anthropic API / Claude Agent SDK / Gemini)
├── cache.py             # Redis cache client
├── errors.py            # Custom exceptions
├── job/
│   ├── models.py        # Job table, JobStatus enum, API schemas
│   ├── routes.py        # API endpoints
│   └── service.py       # Job CRUD
├── serp/
│   ├── models.py        # SERP data models
│   └── client.py        # Mock + real SERP providers
└── article/
    ├── models.py        # BrandVoice, SeoMetaOptions, KeywordDistribution, quality models
    ├── pipeline.py      # State machine runner, markdown parser, merge logic
    ├── prompts.py       # LLM prompt templates, brand voice formatting
    ├── scorer.py        # 6 algorithmic scoring functions + AI detection constants
    ├── scrubber.py      # Content post-processor (filler removal, word subs, paragraph splitting)
    └── schema.py        # JSON-LD generation, featured snippet detection
```
