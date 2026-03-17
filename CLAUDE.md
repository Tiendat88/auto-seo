# CLAUDE.md

## Project

SEO article generator — agent-based pipeline that researches topics, analyzes competitors, and generates optimized articles with quality scoring, content humanization, and schema markup. FastAPI backend + Typer CLI.

## Stack

- **Python 3.12+**, FastAPI, SQLAlchemy async (PostgreSQL prod, SQLite tests), Pydantic v2
- **LLM**: Quad backend via `app/llm.py` — Anthropic API (with tool use), Claude Agent SDK (`max_turns=50`), OpenAI Codex SDK, Google Gemini (with tool use)
- **CLI**: Typer + Rich (`autoseo` entrypoint, bare command shows help via `invoke_without_command`)
- **Cache**: Redis (`app/cache.py`)
- **Deps**: `textstat` (readability metrics), `google-genai` (Gemini), `openai-codex-sdk` (OpenAI Codex), `firecrawl` (SERP content fetching)
- **Lint**: `ruff` (line-length=100, rules: E/F/I/N/W)
- **Tests**: pytest + pytest-asyncio (asyncio_mode="auto"), **145 tests** across 8 files

## Architecture

### Pipeline (`app/article/pipeline.py`)

State machine: `RESEARCHING → PLANNING → GENERATING → SCORING → REVIEWING → [EDITING] → COMPLETED`

- **Single-call generation**: Full article + FAQ in one `generate_text` call, parsed via `_parse_article_markdown`, then scrubbed via `scrub_article()`
- **Planning step**: Two-phase `planning_step` — multi-provider analysis (council fans out competitor analysis in parallel), then single-provider outline with embedded `ArticleBrief`
- **Brand voice**: Optional `BrandVoice` injected into outline/generate/edit prompts via `format_brand_voice()`
- **Hybrid scoring**: 7 algorithmic + 6 LLM = 13 dimensions, weighted average (`word_count_target` at 2x via `DIMENSION_WEIGHTS`)
- **Token tracking**: `LlmClient._usage` accumulates `TokenUsage` per call with cost estimation via `MODEL_PRICING`; pipeline drains per step into `job.usage_data` JSON column
- **Multi-provider council**: `get_llm_council()` returns ALL configured providers as equal peers; analysis, scoring + review fan out to every provider in parallel, results averaged/merged. Scorer/reviewer feedback grouped by number ("Scorer 1", "Reviewer 2") — no model names in edit prompts
- **Event system**: `job.events_data` JSON column — pipeline appends structured events (LLM calls, results, scrub stats, timing, cache hits). Cleared on completion unless `PERSIST_EVENTS=true`
- **Edit loop**: If score/review fails → edit in place (with word count constraint) → re-score → re-review (capped at `max_revisions`)
- **Sub-step visibility**: Generate and score steps update `current_step` with sub-steps (`generating:article`, `generating:metadata`, `scoring:algorithmic`, `scoring:llm`) for CLI progress tracking
- **Word count enforcement**: Prompt constraint (±20% target), steeper scoring curve (>200% = 0.0), `word_count_target` at 2x weight, edit prompt includes trim instructions on overshoot

### Scoring dimensions

| Type | Dimensions | Source |
|------|-----------|--------|
| Algorithmic | keyword_usage, heading_structure, word_count_target, readability_metrics, humanity, keyword_distribution, differentiation_delivery | `app/article/scorer.py` |
| LLM | content_depth, differentiation, accuracy, consistency, readability, actionability | 3 parallel `_ScorePair` calls |

### Content scrubber (`app/article/scrubber.py`)

Post-processes articles after generation and editing. Returns `(ArticleContent, ScrubStats)`:
- **Modifies**: zero-width Unicode strip, AI filler opener removal (~5 patterns), long paragraph splitting (>6 sentences)
- **Counts only** (logged, not scrubbed): em-dashes, double-hyphens, AI-favored words (leverage, delve, etc.)
- Prompt handles style enforcement (tells LLM to avoid em-dashes and AI words upfront)

### SEO outputs (`app/article/schema.py`)

- **JSON-LD**: Article + FAQPage schema markup, computed lazily in `build_result()`
- **Snippet detection**: List, table, definition, Q&A opportunities — also lazy in `build_result()`
- **Meta options**: 5 title tags + 5 meta descriptions via `SeoMetaOptions` (parallel LLM call in `generate_step`)

### Key files

| Path | Purpose |
|------|---------|
| `app/article/pipeline.py` | Pipeline runner, step functions (incl. two-phase planning_step), markdown parser, merge logic |
| `app/article/prompts.py` | All LLM prompt templates + `format_brand_voice`, `meta_options_prompt` |
| `app/article/models.py` | Pydantic models (BrandVoice, SeoMetaOptions, KeywordDistribution, etc.) |
| `app/article/scorer.py` | 7 algorithmic scoring functions + AI_FILLER_PHRASES/VAGUE_WORDS constants |
| `app/article/scrubber.py` | Content post-processor (filler removal, paragraph splitting, AI word/em-dash counting) |
| `app/article/tools.py` | LLM tool definitions for Anthropic + Gemini tool use (research, content fetching) |
| `app/serp/fetcher.py` | Firecrawl integration for SERP content fetching |
| `app/article/schema.py` | JSON-LD generation, snippet opportunity detection |
| `app/llm.py` | LlmClient (quad backend), `get_llm_council()`, `MODEL_PRICING`, call logging |
| `app/job/models.py` | Job ORM model (includes `brand_voice_data`, `meta_options_data`), API schemas |
| `app/job/service.py` | Job CRUD, `claim_job_for_resume` (requires `session.refresh` after commit) |
| `app/cli.py` | Typer CLI: generate, watch, resume (409→watch, 400→message), status, result, list, export |
| `app/config.py` | Settings via pydantic-settings |

## Commands

```bash
ruff check app/ tests/                    # Lint
python -m pytest tests/ -x -q             # Test (145 tests)
uvicorn app.main:app --workers 2          # Run server (2 workers: Agent SDK blocks event loop)
autoseo generate "topic" --brand-voice brand.json  # CLI with brand voice
autoseo -v generate "topic"                       # Verbose: stream all pipeline events
autoseo watch <id>                        # Reconnect to running job
autoseo resume <id>                       # Resume failed (or watch if running)
autoseo export <id> article.md            # Export with JSON-LD
```

## Config (env vars / .env)

- `ANTHROPIC_API_KEY` — Anthropic API (if set, uses API backend)
- `OPENAI_API_KEY` — Optional OpenAI API key
- `OPENAI_MODEL` — OpenAI model (default `o3-mini`)
- `OPENAI_CODEX` — Set `true` to use Codex SDK backend (ChatGPT subscription)
- `GOOGLE_API_KEY` — Enables Gemini in the provider council for scoring/review
- `SERP_PROVIDER` — `mock` (default) or `serpapi`
- `DATABASE_URL` — PostgreSQL connection string
- `QUALITY_THRESHOLD` — Min overall score (default 0.8)
- `MAX_REVISIONS` — Edit loop cap (default 10)
- `FIRECRAWL_API_KEY` — Firecrawl API key for SERP content fetching
- `CONTENT_FETCH_TOP_N` — Number of top SERP results to fetch content for (default varies)
- `PERSIST_EVENTS` — Keep pipeline events after completion (default `false`)

## DB migration

Existing databases need manual column addition for new features:
```sql
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS meta_options_data JSON;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS brand_voice_data JSON;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS usage_data JSON;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS events_data JSON;

-- Status rename: analyzing/outlining → planning
UPDATE jobs SET status='planning' WHERE status IN ('analyzing', 'outlining');
```
New databases auto-create via `Base.metadata.create_all` on startup.

## CLI internals

- **Verbose mode** (`--verbose/-v`): global flag, renders pipeline events streamed via `events_data` polling. Shows LLM calls, scoring results per provider, scrub stats, timing, cache hits, cost
- **`ctx.obj`**: dict `{"url": ..., "verbose": ...}` — accessed via `_api_url(ctx)` and `_is_verbose(ctx)`
- **Polling**: `_poll_job` uses 120s httpx timeout + retry on `ReadTimeout` (Agent SDK blocks event loop for minutes)
- **Sub-step display**: `current_step` with `:` separator (e.g., `generating:article`) renders as `Generate (article)...` in progress bar
- **Resume**: 409 → auto-switches to watch mode; 400 → prints error message (e.g., "Job already completed")
- **Watch**: reconnects to any running job, shows completed/failed state if job already finished
- **Token summary**: shows total tokens + estimated cost via `MODEL_PRICING`

## Known issues

- **Agent SDK blocks event loop**: `generate_text` via Agent SDK spawns a subprocess that blocks the async loop for 2-5 min per call. Use `--workers 2` so one worker handles HTTP while the other runs the pipeline. PostgreSQL connections can also stall if the pipeline holds a session open during a blocked call.
- **Stale job recovery**: Jobs interrupted mid-pipeline (e.g., server restart) get stuck in active states like `generating`. Must manually `UPDATE jobs SET status='failed'` before resume works (`claim_job_for_resume` only accepts `failed`/`pending`).
- **`claim_job_for_resume` requires `session.refresh()`**: After the atomic UPDATE + COMMIT, SQLAlchemy expires attributes. Without `refresh()`, accessing `job.updated_at` in `_job_to_response` triggers `MissingGreenlet` (sync lazy load in async context).

## Testing patterns

- In-memory SQLite via `create_async_engine("sqlite+aiosqlite:///:memory:")`
- Conftest fixtures: `sample_job`, `sample_outline` (with brief), `sample_article`, etc.
- Pipeline tests mock `generate_text`/`generate_structured` with `_smart_generate_structured` dispatcher
- Pipeline tests must include `SeoMetaOptions: _make_meta_options()` in model maps (parallel LLM call)
- Pipeline tests patch `get_llm_council` (return `[mock_llm]`) and `settings` (control threshold)
- Mock LLM requires: `drain_usage = MagicMock(return_value=[])` and `drain_call_log = MagicMock(return_value=[])`
- Threshold for edit loop tests: use 0.6 (weighted scoring with word_count at 2x makes 0.75 too strict for test fixtures)
- Dimension count assertion: 9 = 7 algo + 2 merged LLM (single-provider council)
