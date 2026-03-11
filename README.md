# SEO Article Generator

Backend service that generates SEO-optimized articles using an agent-based pipeline. Takes a topic, analyzes the competitive SERP landscape, and produces a publish-ready article with SEO metadata, keyword analysis, linking suggestions, and quality scoring.

## Quick Start

```bash
# 1. Start PostgreSQL and Redis
docker-compose up -d

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 4. Start the server
uvicorn app.main:app --reload

# 5. Generate an article
seo-cli generate "best productivity tools for remote teams"
```

## Architecture

```
POST /jobs → Job(PENDING) → Background pipeline:
  RESEARCHING → ANALYZING → OUTLINING → GENERATING → SCORING → COMPLETED
       ↑                                                  │
       └──────── revision loop (max 2) ──────────────────┘
```

**Linear state machine pipeline** — each step saves intermediate results to the database as JSON. If the process crashes, jobs resume from the last completed step.

### Pipeline Steps

1. **Research** — Fetch top 10 SERP results for the topic (mock or real SerpAPI)
2. **Analyze** — LLM extracts themes, keywords, content gaps, and search intent from SERP data
3. **Outline** — LLM generates a structured outline with word count budgets per section
4. **Generate** — LLM writes article section-by-section with transition context threading
5. **Score** — Hybrid quality scoring (algorithmic + LLM). Below threshold triggers revision loop

### Tech Stack

| Component | Choice |
|-----------|--------|
| API | FastAPI |
| Database | PostgreSQL + async SQLAlchemy |
| LLM | Anthropic Claude (AsyncAnthropic) |
| SERP | Mock provider (default) / SerpAPI |
| Cache | Redis |
| CLI | Typer + Rich |

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

### Check status

```bash
curl http://localhost:8000/api/jobs/{job_id}
```

## CLI Client

```bash
seo-cli generate "best productivity tools" --words 1500
seo-cli status <job-id>
seo-cli result <job-id> --format md
seo-cli list --status completed
seo-cli resume <job-id>
```

## Output Structure

The completed job returns an `ArticleResult` with:

- **seo_metadata** — title tag (<60 chars), meta description (<160 chars), primary keyword, slug
- **content** — article sections with heading hierarchy (H1/H2/H3), FAQ items, total word count
- **keyword_analysis** — primary/secondary keyword counts, density, and placement locations
- **links** — 3-5 internal link suggestions, 2-4 external reference suggestions
- **quality** — overall score (0-1), per-dimension scores, revision instructions if below threshold
- **competitive_analysis** — themes, keywords, content gaps from SERP analysis
- **outline** — structured outline with per-section word budgets

See [`examples/sample_output.json`](examples/sample_output.json) for a complete example.

## Testing

```bash
pytest tests/ -v
```

**67 tests** across 5 test files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 24 | Pydantic validation, serialization, constraints, negative cases |
| `test_api.py` | 11 | API endpoints, error handling, CRUD, resume edge cases |
| `test_pipeline.py` | 8 | State machine, resume logic, failure handling, revision loop |
| `test_quality.py` | 12 | Algorithmic SEO scoring functions |
| `test_seo.py` | 12 | SEO constraint validation |

Tests use in-memory SQLite (no PostgreSQL required) and mock LLM/SERP providers.

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for LLM calls |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Anthropic model to use |
| `SERP_PROVIDER` | `mock` | `mock` or `serpapi` |
| `SERPAPI_KEY` | — | Required if `SERP_PROVIDER=serpapi` |
| `DATABASE_URL` | `postgresql+asyncpg://seo:seo@localhost:5432/seo_agent` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for caching |
| `QUALITY_THRESHOLD` | `0.7` | Minimum quality score (0-1) |
| `MAX_REVISIONS` | `2` | Max revision loops on quality failure |

## Design Decisions

**State machine over agent framework** — The pipeline is sequential (SERP → analyze → outline → generate → score). A clean state machine with DB persistence is simpler, more testable, and easier to debug than LangGraph or similar frameworks.

**Section-by-section generation** — Each outline heading generates one section via a separate LLM call with transition context from the previous section. This produces more balanced coverage than generating the entire article in one call.

**Hybrid quality scoring** — Algorithmic checks (keyword density, heading hierarchy, word count) are deterministic and testable. LLM-based checks (content depth, readability) catch subjective quality issues. Combined score with configurable threshold triggers revision loops.

**Resume = re-enter state machine** — Each step's output is persisted to DB before advancing. On crash/failure, `_determine_resume_index()` finds the first missing output and resumes from there. No complex checkpointing needed.

**Redis caching** — SERP results cached 24h, LLM responses cached 1h. Graceful degradation: if Redis is down, caching is silently disabled.

**Mock SERP by default** — The `MockSerpProvider` generates realistic results based on the topic string, so the system works end-to-end without API keys. Swap to real SerpAPI via config.

## Project Structure

```
app/
├── main.py              # FastAPI app, lifespan
├── config.py            # pydantic-settings
├── db.py                # Async SQLAlchemy engine/sessions
├── llm.py               # AsyncAnthropic wrapper
├── cache.py             # Redis cache client
├── errors.py            # Custom exceptions
├── job/
│   ├── models.py        # Job table, API schemas
│   ├── routes.py        # API endpoints
│   └── service.py       # Job CRUD
├── serp/
│   ├── models.py        # SERP data models
│   └── client.py        # Mock + real SERP providers
└── article/
    ├── models.py        # Article, SEO, quality models
    ├── pipeline.py      # State machine runner
    ├── prompts.py       # LLM prompt templates
    └── scorer.py        # Quality scoring functions
```
