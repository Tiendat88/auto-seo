# SEO Article Generator

Backend service that generates SEO-optimized articles using an agent-based pipeline. It also includes AEO scoring/query fan-out tooling and brand mention monitoring across AI platforms. For article generation, it takes a topic, analyzes the competitive SERP landscape, and produces a publish-ready article with SEO metadata, keyword analysis, linking suggestions, quality scoring, JSON-LD schema markup, and content humanization.

## Quick Start

```bash
# 1. Start PostgreSQL and Redis
docker-compose up -d

# 2. Install dependencies
uv sync --extra dev --python 3.12

# 3. Configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and any optional provider keys you plan to use.
# `VOYAGE_API_KEY` is required for fan-out gap analysis when you pass `--content`.

# 4. Optional runtime assets
uv run playwright install chromium              # Needed for `brand --mode browser`
uv run python -m spacy download en_core_web_sm # Needed for AEO checks and the full test suite

# 5. Start the server
uv run uvicorn app.main:app --workers 2

# 6. Generate an article
uv run autoseo generate "best productivity tools for remote teams"
```

## Architecture

```text
POST /jobs → Job(PENDING) → Background pipeline:
  RESEARCHING → PLANNING → GENERATING → SCORING → REVIEWING → COMPLETED
                                            ↑                      │
                                            └── edit loop (max 10)─┘
```

**Linear state machine pipeline** — each step saves intermediate results to the database as JSON. If the process crashes, startup recovery marks in-flight jobs as failed so they can be resumed from the last completed step.

### Pipeline Steps

1. **Research** — Fetch top 10 SERP results for the topic (mock or real SerpAPI). Optionally scrape page content from top results via Firecrawl for deeper analysis.
2. **Plan** — Two-phase step: (a) multi-provider competitive analysis fans out to all configured providers in parallel, extracts themes, keywords, content gaps, and search intent; analyses are merged by consensus. (b) single-provider outline generation with editorial brief, per-section word budgets, and optional brand voice alignment.
3. **Generate** — One LLM call produces the full article with FAQ, parsed from markdown. Parallel calls generate SEO metadata, link suggestions, and 5 meta tag options. Content is then scrubbed for filler openers, zero-width Unicode, and long paragraphs.
4. **Score** — Hybrid quality scoring: 7 algorithmic checks plus 6 LLM-evaluated dimensions.
5. **Review** — Holistic editorial review with issue-level feedback.
6. **Edit** — If score or review fails, the article is edited in place, scrubbed again, and re-scored/re-reviewed until it passes or hits `MAX_REVISIONS`.

### Multi-Provider Council

When multiple LLM backends are configured (Anthropic, Gemini, Codex), the pipeline forms a council via `get_llm_council()`. Note: standard `OPENAI_API_KEY` alone does **not** join the council — only `OPENAI_CODEX=true` adds the OpenAI backend:

- **Analysis**: all providers analyze competitors in parallel; results are merged by consensus.
- **Scoring**: LLM dimensions fan out to all providers and are averaged by dimension.
- **Review**: issues from all providers are collected; the result passes only if no critical/major issues remain.

Scorer and reviewer feedback is numbered (`Scorer 1`, `Reviewer 2`) so model names do not leak into edit prompts.

### Tech Stack

| Component | Choice |
|-----------|--------|
| API | FastAPI |
| Database | PostgreSQL + async SQLAlchemy |
| LLM | Anthropic Claude (API + tool use), Claude Agent SDK, OpenAI Codex SDK, Google Gemini (+ tool use) |
| SERP/content | Mock provider (default) / SerpAPI + Firecrawl Python SDK |
| Browser automation | Playwright (lazy-loaded for brand monitor browser mode; includes Grok) |
| Cache | Redis |
| CLI | Typer + Rich |
| NLP | textstat, spaCy, VoyageAI embeddings, BeautifulSoup |

## API Endpoints

```text
POST /api/jobs/                  Create article generation job
GET  /api/jobs/                  List jobs (filter by status, paginated)
GET  /api/jobs/{id}              Get job status and result
POST /api/jobs/{id}/resume       Resume a failed job
POST /api/brand-monitor/analyze  Analyze brand mentions across AI platforms
POST /api/aeo/analyze            Score content for AEO readiness
POST /api/aeo/fanout             Generate sub-queries and optional gap analysis
GET  /health                     Health check
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
uv run autoseo                                              # Show help
uv run autoseo generate "best productivity tools" --words 1500
uv run autoseo generate "topic" --brand-voice brand.json   # With brand voice context
uv run autoseo -v generate "topic"                         # Verbose: stream pipeline events
uv run autoseo status <job-id>
uv run autoseo watch <job-id>                              # Reconnect to a running job
uv run autoseo result <job-id>                             # Full markdown render
uv run autoseo result <job-id> --summary                   # Compact quality summary
uv run autoseo result <job-id> --json                      # Raw JSON output
uv run autoseo list --status completed
uv run autoseo resume <job-id>                             # Resume failed job (or watch if running)
uv run autoseo export <job-id> article.md                  # Markdown with JSON-LD schema
uv run autoseo aeo tests/fixtures/article_good.html --json
uv run autoseo fanout "best CRM for startups" --content https://example.com --json
uv run autoseo brand "Notion" "best note-taking app"            # Browser mode is the default
```

## Output Structure

The completed job returns an `ArticleResult` with:

- **seo_metadata** — title tag (<60 chars), meta description (<160 chars), primary keyword, slug
- **content** — article sections with heading hierarchy (H1/H2/H3), FAQ items, total word count
- **keyword_analysis** — primary/secondary keyword counts, density, placement locations, and section-level keyword distribution with evenness score
- **links** — 3-5 internal link suggestions and 2-4 external reference suggestions
- **quality** — overall score (0-1), 13 per-dimension scores, revision instructions if below threshold
- **review** — pass/fail with issue-level feedback and strengths
- **schema_markup** — Article + FAQPage JSON-LD for rich snippets
- **meta_options** — 5 alternative title tags + 5 alternative meta descriptions
- **snippet_opportunities** — detected list, table, definition, and Q&A opportunities
- **competitive_analysis** — themes, keywords, and content gaps from SERP analysis
- **outline** — structured outline with editorial brief and per-section word budgets

## Testing

```bash
uv run pytest tests/ -x -q
```

**249 tests** across 15 files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 48 | Pydantic validation, serialization, constraints, BrandVoice, SeoMetaOptions, KeywordDistribution, SchemaMarkup |
| `test_pipeline.py` | 34 | State machine, resume, markdown parser, edit loop, merge functions, multi-provider scoring/review |
| `test_brand.py` | 33 | Brand monitor routes, aggregation, lazy Playwright import, dependency handling |
| `test_aeo.py` | 32 | AEO parser, checks, aggregation, URL/text input handling |
| `test_quality.py` | 17 | Algorithmic scoring: keyword usage, heading structure, word count, readability, humanity, keyword distribution, differentiation delivery |
| `test_fanout.py` | 17 | Fan-out prompt, parsing, gap analysis, provider/model override |
| `test_api.py` | 14 | API endpoints, error handling, CRUD, resume edge cases |
| `test_seo.py` | 12 | SEO constraint validation |
| `test_scrubber.py` | 12 | Content scrubber: zero-width removal, filler removal, paragraph splitting, list normalization, AI word/em-dash counting |
| `test_llm.py` | 11 | Provider selection, Gemini backend routing, tool use, usage/cost plumbing |
| `test_schema.py` | 9 | JSON-LD schema generation, FAQPage markup, snippet detection |
| `test_cli.py` | 3 | CLI command registration, help output |
| `test_prompts.py` | 3 | Prompt template rendering, brand voice formatting |
| `test_db.py` | 2 | Postgres advisory-lock init path, non-Postgres init path |
| `test_serp_fetcher.py` | 2 | Firecrawl Python SDK contract regression coverage |

Tests use in-memory SQLite and mock LLM/SERP providers. The full suite also expects the spaCy model `en_core_web_sm` to be installed.

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key (if set, uses API backend; otherwise falls back to Claude Agent SDK) |
| `GOOGLE_API_KEY` | — | Enables Gemini in the provider council and brand API fetches |
| `OPENAI_API_KEY` | — | Enables OpenAI API fetches for brand monitoring (`chatgpt`) |
| `PERPLEXITY_API_KEY` | — | Enables Perplexity API fetches for brand monitoring |
| `LLM_MODEL` | `claude-sonnet-4-6` | Anthropic model to use |
| `GEMINI_MODEL` | `gemini-3-flash-preview` | Default Gemini model for non-writing tasks |
| `GEMINI_WRITING_MODEL` | `gemini-3-pro-preview` | Gemini model used only for article draft + edit generation |
| `OPENAI_MODEL` | `o3-mini` | OpenAI model to use |
| `OPENAI_CODEX` | `false` | Enable Codex SDK backend (ChatGPT subscription) |
| `SERP_PROVIDER` | `mock` | `mock` or `serpapi` |
| `SERPAPI_KEY` | — | Required if `SERP_PROVIDER=serpapi` |
| `FIRECRAWL_API_KEY` | — | Firecrawl API key for SERP content fetching and URL-backed fan-out content fetches |
| `VOYAGE_API_KEY` | — | VoyageAI API key for AEO fan-out gap analysis embeddings |
| `VOYAGE_EMBEDDING_MODEL` | `voyage-4-large` | VoyageAI embedding model for AEO fan-out gap analysis |
| `CONTENT_FETCH_TOP_N` | `10` | Number of top SERP results to fetch content for |
| `DATABASE_URL` | `postgresql+asyncpg://seo:seo@localhost:5432/seo_agent` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for caching |
| `QUALITY_THRESHOLD` | `0.8` | Minimum quality score (0-1) to skip edit loop |
| `MAX_REVISIONS` | `10` | Max edit loop iterations on quality/review failure |
| `AEO_SIMILARITY_THRESHOLD` | `0.72` | Cosine similarity threshold for fan-out gap analysis |
| `DEBUG` | `false` | Enable SQLAlchemy debug logging |
| `PERSIST_EVENTS` | `false` | Keep pipeline events after completion |

## Operational Notes

- Run the CLI as `uv run autoseo ...` after `uv sync`; it uses the project script from the synced environment.
- `brand` defaults to browser mode and currently targets ChatGPT, Perplexity, Gemini, and Grok.
- `brand --mode browser` needs Playwright browser binaries even though the Python package is already in project dependencies.
- `brand` fetch and `brand` analysis are separate stages. A `503 Brand analysis failed` response can come from the analyzer LLM after fetch succeeds.
- `app/db.py` serializes schema bootstrap with a Postgres advisory lock, so `uvicorn --workers 2` is safe on a fresh database.
- `app/serp/fetcher.py` uses the Firecrawl Python SDK contract (`only_main_content=True`), not the raw REST API's camelCase request fields.
- `app/aeo/fanout.py` uses VoyageAI `voyage-4-large` embeddings with `input_type="query"` and `input_type="document"` for semantic gap analysis.
- Article drafting and edit-loop rewrites use `GEMINI_WRITING_MODEL`, while metadata, link suggestions, council review/scoring, and other default Gemini work stay on `GEMINI_MODEL`.

## Design Decisions

**State machine over agent framework** — The pipeline is sequential (SERP → plan → generate → score → review). A clean state machine with DB persistence is simpler, more testable, and easier to debug than a generic agent orchestration framework.

**Single-call article generation** — The full article (including FAQ) is generated in one LLM call and parsed from markdown. This produces more coherent narrative flow than section-by-section generation.

**Two-phase planning** — Analysis and outlining are merged into one pipeline state (`PLANNING`). Phase 1 fans out competitive analysis to all configured providers, then merges results. Phase 2 turns that merged analysis into a single outline with editorial brief.

**Hybrid quality scoring** — Algorithmic checks cover deterministic SEO/readability signals while LLM checks handle subjective quality, actionability, and consistency.

**Content scrubber** — Post-processes generated content to strip zero-width Unicode, remove filler openers, and split long paragraphs. It logs AI-favored words and dash patterns without automatically deleting them.

**Brand voice context** — Optional `BrandVoice` data is injected into outline, generation, and editing prompts without changing the pipeline shape.

**Edit loop over regeneration** — Failed content is edited in place instead of regenerated from scratch, which preserves good sections and focuses work on the weak parts.

**Resume from persisted state** — Each step persists output before advancing. Orphaned jobs are marked failed on startup, and resume re-enters the state machine from the first missing output.

**Redis caching** — SERP results are cached for 24h and LLM responses for 1h. If Redis is unavailable, caching is skipped without taking down the app.

**Mock SERP by default** — The system works end to end without external SERP credentials, then swaps to SerpAPI when configured.

## Usage Guide

### Generate your first article

```bash
# Start the server (use --workers 2 to prevent Agent SDK from blocking requests)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Generate with live progress tracking
uv run autoseo generate "best project management tools for startups 2026" --words 1500
```

The CLI shows a live progress bar with step-by-step output as the pipeline runs. Sub-steps like `Generate (article)` and `Score (llm)` show what is happening inside long-running stages.

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
uv run autoseo generate "topic" --brand-voice brand.json
```

### Monitor and manage jobs

```bash
uv run autoseo watch <job-id>
uv run autoseo resume <job-id>
uv run autoseo result <job-id> --summary
uv run autoseo export <job-id> article.md
```

### AEO and brand utilities

```bash
# Score existing content for AEO readiness
uv run autoseo aeo tests/fixtures/article_good.html --json

# Generate fan-out sub-queries and gap analysis from a URL
uv run autoseo fanout "best CRM for startups" --content https://example.com --json

# Monitor brand mentions through real browser UIs (default)
uv run autoseo brand "Notion" "best note-taking app" --json

# Force provider API mode instead
uv run autoseo brand "Notion" "best note-taking app" --mode api --json
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
| Research | ~1s | SERP fetch (mock: instant, SerpAPI: 2-3s) + Firecrawl scraping |
| Plan | ~20s | Multi-provider analysis (with tools) + outline generation |
| Generate | 2-5 min | Article LLM call + 3 parallel metadata calls |
| Score | ~30s | 7 algorithmic + 6 LLM scoring dimensions |
| Review | ~30s | Multi-provider editorial review |
| Edit loop | 3-8 min | Up to 10 revision cycles if quality/review fails |

### Production deployment

```bash
# Required: PostgreSQL + Redis
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Recommended env vars
ANTHROPIC_API_KEY=sk-...          # Required for LLM calls
GOOGLE_API_KEY=...                # Optional: enables multi-provider council
FIRECRAWL_API_KEY=...             # Optional: enables SERP content fetching
SERP_PROVIDER=serpapi             # Real SERP data
SERPAPI_KEY=...                   # Required with serpapi provider
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
QUALITY_THRESHOLD=0.8             # Min score to skip editing
MAX_REVISIONS=10                  # Edit loop cap
```

> **Note**: Use `--workers 2` with uvicorn. The Claude Agent SDK blocks the event loop during long generation calls (~5 min). Multiple workers keep the API responsive, and startup now serializes schema bootstrap with a Postgres advisory lock so fresh multi-worker startup is safe.

## Project Structure

```text
app/
├── main.py                 # FastAPI app, lifespan, startup recovery
├── config.py               # pydantic-settings
├── db.py                   # Async SQLAlchemy engine/sessions + advisory-lock init
├── llm.py                  # LlmClient (Anthropic API / Claude Agent SDK / Codex SDK / Gemini)
├── cache.py                # Redis cache client
├── errors.py               # Custom exceptions
├── aeo/
│   ├── routes.py           # /api/aeo/analyze and /api/aeo/fanout
│   ├── models.py           # AEO Pydantic models (CheckResult, SubQuery, FanOutResponse, etc.)
│   ├── parser.py           # URL/text parsing and boilerplate stripping (BeautifulSoup)
│   ├── checks.py           # AEO scoring checks (spaCy, textstat)
│   ├── fanout.py           # Sub-query generation and gap analysis
│   └── store.py            # AEO persistence (AeoAnalysis ORM table) + Redis cache helpers
├── brand/
│   ├── routes.py           # /api/brand-monitor/analyze
│   ├── models.py           # Brand monitor Pydantic models
│   ├── analyzer.py         # Structured brand mention analysis
│   ├── fetcher.py          # API-mode platform fetches
│   ├── gather.py           # Partial-success gathering utility for parallel fetches
│   └── browser_fetcher.py  # Browser-mode platform fetches via Playwright
├── job/
│   ├── models.py           # Job table, JobStatus enum, API schemas
│   ├── routes.py           # API endpoints
│   └── service.py          # Job CRUD
├── serp/
│   ├── models.py           # SERP data models
│   ├── client.py           # Mock + real SERP providers
│   └── fetcher.py          # Firecrawl Python SDK integration
└── article/
    ├── models.py           # BrandVoice, SeoMetaOptions, KeywordDistribution, quality models
    ├── constants.py        # Shared regex/word lists
    ├── pipeline.py         # State machine runner, step functions, markdown parser, merge logic
    ├── prompts.py          # LLM prompt templates, brand voice formatting
    ├── scorer.py           # 7 algorithmic scoring functions + full_text() helper
    ├── scrubber.py         # Content post-processor
    ├── tools.py            # LLM tool definitions for Anthropic + Gemini tool use
    └── schema.py           # JSON-LD generation, featured snippet detection
```
