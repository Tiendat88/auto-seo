# CLAUDE.md

## Project

SEO article generator — agent-based pipeline that researches topics, analyzes competitors, and generates optimized articles with quality scoring, content humanization, and schema markup. FastAPI backend + Typer CLI.

## Stack

- **Python 3.12+**, FastAPI, SQLAlchemy async (PostgreSQL prod, SQLite tests), Pydantic v2
- **LLM**: Triple backend via `app/llm.py` — Anthropic API, Claude Agent SDK (`max_turns=50`), Google Gemini
- **CLI**: Typer + Rich (`autoseo` entrypoint, bare command shows help via `invoke_without_command`)
- **Cache**: Redis (`app/cache.py`)
- **Deps**: `textstat` (readability metrics), `google-genai` (Gemini)
- **Lint**: `ruff` (line-length=100, rules: E/F/I/N/W)
- **Tests**: pytest + pytest-asyncio (asyncio_mode="auto"), **142 tests** across 8 files

## Architecture

### Pipeline (`app/article/pipeline.py`)

State machine: `RESEARCHING → ANALYZING → OUTLINING → GENERATING → SCORING → REVIEWING → [EDITING] → COMPLETED`

- **Single-call generation**: Full article + FAQ in one `generate_text` call, parsed via `_parse_article_markdown`, then scrubbed via `scrub_article()`
- **Editorial brief**: `ArticleBrief` embedded in `ArticleOutline` (not a separate step)
- **Brand voice**: Optional `BrandVoice` injected into outline/generate/edit prompts via `format_brand_voice()`
- **Hybrid scoring**: 6 algorithmic + 6 LLM = 12 dimensions total, simple average for overall score
- **Multi-provider**: When `GOOGLE_API_KEY` set, scoring + review run on both Claude and Gemini in parallel; results averaged/merged
- **Edit loop**: If score/review fails → edit in place → re-score → re-review (capped at `max_revisions`)
- **Sub-step visibility**: Generate and score steps update `current_step` with sub-steps (`generating:article`, `generating:metadata`, `scoring:algorithmic`, `scoring:llm`) for CLI progress tracking

### Scoring dimensions

| Type | Dimensions | Source |
|------|-----------|--------|
| Algorithmic | keyword_usage, heading_structure, word_count_target, readability_metrics, humanity, keyword_distribution | `app/article/scorer.py` |
| LLM | content_depth, differentiation, accuracy, consistency, readability, actionability | 3 parallel `_ScorePair` calls |

### Content scrubber (`app/article/scrubber.py`)

Post-processes articles after generation and editing. Moderate aggressiveness:
- Zero-width Unicode removal, em-dash → `--`, AI filler phrase removal (~5 openers), word substitutions (~10: leverage→use, delve→explore, etc.), paragraph splitting (>4 sentences)

### SEO outputs (`app/article/schema.py`)

- **JSON-LD**: Article + FAQPage schema markup, computed lazily in `build_result()`
- **Snippet detection**: List, table, definition, Q&A opportunities — also lazy in `build_result()`
- **Meta options**: 5 title tags + 5 meta descriptions via `SeoMetaOptions` (parallel LLM call in `generate_step`)

### Key files

| Path | Purpose |
|------|---------|
| `app/article/pipeline.py` | Pipeline runner, step functions, markdown parser, merge logic |
| `app/article/prompts.py` | All LLM prompt templates + `format_brand_voice`, `meta_options_prompt` |
| `app/article/models.py` | Pydantic models (BrandVoice, SeoMetaOptions, KeywordDistribution, etc.) |
| `app/article/scorer.py` | 6 algorithmic scoring functions + AI_FILLER_PHRASES/VAGUE_WORDS constants |
| `app/article/scrubber.py` | Content post-processor (filler removal, word subs, paragraph splitting) |
| `app/article/schema.py` | JSON-LD generation, snippet opportunity detection |
| `app/llm.py` | LlmClient (triple backend), `get_secondary_llm()` |
| `app/job/models.py` | Job ORM model (includes `brand_voice_data`, `meta_options_data`), API schemas |
| `app/job/service.py` | Job CRUD, `claim_job_for_resume` (requires `session.refresh` after commit) |
| `app/cli.py` | Typer CLI: generate, watch, resume, status, result, list, export |
| `app/config.py` | Settings via pydantic-settings |

## Commands

```bash
ruff check app/ tests/                    # Lint
python -m pytest tests/ -x -q             # Test (142 tests)
uvicorn app.main:app --workers 2          # Run server (2 workers: Agent SDK blocks event loop)
autoseo generate "topic" --brand-voice brand.json  # CLI with brand voice
autoseo watch <id>                        # Reconnect to running job
autoseo resume <id>                       # Resume failed (or watch if running)
autoseo export <id> article.md            # Export with JSON-LD
```

## Config (env vars / .env)

- `ANTHROPIC_API_KEY` — Anthropic API (if set, uses API backend)
- `GOOGLE_API_KEY` — Enables Gemini as secondary provider for scoring/review
- `SERP_PROVIDER` — `mock` (default) or `serpapi`
- `DATABASE_URL` — PostgreSQL connection string
- `QUALITY_THRESHOLD` — Min overall score (default 0.7)
- `MAX_REVISIONS` — Edit loop cap (default 2)

## DB migration

Existing databases need manual column addition for new features:
```sql
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS meta_options_data JSON;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS brand_voice_data JSON;
```
New databases auto-create via `Base.metadata.create_all` on startup.

## Known issues

- **Agent SDK blocks event loop**: Long `generate_text` calls (5+ min) block the uvicorn async loop. Use `--workers 2` to keep the API responsive during pipeline runs.
- **Stale job recovery**: Jobs interrupted mid-pipeline (e.g., server restart) get stuck in active states like `generating`. Must manually `UPDATE jobs SET status='failed'` before resume works (`claim_job_for_resume` only accepts `failed`/`pending`).
- **`claim_job_for_resume` requires `session.refresh()`**: After the atomic UPDATE + COMMIT, SQLAlchemy expires attributes. Without `refresh()`, accessing `job.updated_at` in `_job_to_response` triggers `MissingGreenlet` (sync lazy load in async context).

## Testing patterns

- In-memory SQLite via `create_async_engine("sqlite+aiosqlite:///:memory:")`
- Conftest fixtures: `sample_job`, `sample_outline` (with brief), `sample_article`, etc.
- Pipeline tests mock `generate_text`/`generate_structured` with `_smart_generate_structured` dispatcher
- Pipeline tests must include `SeoMetaOptions: _make_meta_options()` in model maps (parallel LLM call)
- Pipeline tests patch `get_secondary_llm` (return None for single-provider) and `settings` (control threshold)
- Threshold for edit loop tests: use 0.75+ (6 algo dims inflate overall even with 0.0 LLM scores)
- Dimension count assertion: 8 = 6 algo + 2 merged LLM (single provider)
