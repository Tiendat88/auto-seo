# Examples

Real outputs from autoseo's article generation, brand monitoring, AEO scoring, and fan-out analysis. All JSON files are produced by real API calls (Gemini, Perplexity, Firecrawl, Voyage).

## Brand Monitoring (`brand/`)

Track how AI platforms mention your brand across ChatGPT, Perplexity, Gemini, and Claude.

| File | What it shows |
|------|--------------|
| `auto-discovery-notion.json` | Full pipeline: URL scrape, competitor identification, 6 auto-generated prompts, fetch from 2 providers, analysis with scores and rankings |
| `auto-discovery-notion.log` | Step-by-step trace: scrape, competitors found, prompts generated, fetch results, scores |
| `single-query-notion.json` | Single-query analysis: "What are the best note-taking apps?" with visibility scores, competitor rankings, and provider comparison |
| `single-query-linear.json` | Same flow for Linear — "best project management tool for engineering teams" |
| `multi-query-notion.json` | Two-prompt analysis combining ranking + comparison queries |
| `scoring-with-rankings.json` | Detailed scoring breakdown: visibility, share of voice, sentiment, position, plus competitor rankings and provider comparison matrix |
| `discovery-prompts-notion.json` | The 14 auto-generated prompts across ranking, comparison, alternatives, and recommendations categories |
| `notion-api.json` | CLI-generated analysis (`autoseo brand "Notion" "best note-taking app" --mode api --json`) |

## Article Generation (`pipeline/` + `articles/`)

Research topics, analyze competitors, generate optimized articles with quality scoring.

| File | What it shows |
|------|--------------|
| `pipeline/generated-article-short.json` | Complete pipeline output for an 800-word article: SERP research, competitive analysis, outline, article, 13-dimension quality scores, review |
| `articles/best-productivity-tools-for-remote-teams.md` | The generated article in markdown |
| `pipeline/generated-article-short.log` | Pipeline trace with timing |
| `pipeline/generated-article-medium.json` | Same for a 1500-word article on RAG implementation |
| `articles/how-to-implement-retrieval-augmented-generation.md` | The generated article |
| `pipeline/quality-dimensions.json` | All 13 scoring dimensions (7 algorithmic + 6 LLM) with scores and feedback |
| `pipeline/planning-output.json` | Competitive analysis + article outline from the planning step |
| `articles/*.md` | Gallery of final exported articles from CLI runs |

See `article-workflows/` for full CLI workflow traces (generate, watch, status, result, export) per article.

## AEO Content Scoring (`aeo/`)

Score content for Answer Engine Optimization readiness (0-100) across direct answer quality, heading hierarchy, and readability.

| File | What it shows |
|------|--------------|
| `score-good-article.json` | Well-structured RAG article: scores, band label, per-check breakdown |
| `score-bad-article.json` | Poorly structured article for comparison |
| `score-medium-article.json` | Middle-ground article |
| `score-well-structured-markdown.json` | Markdown with proper H1/H2/H3 hierarchy |
| `score-poorly-structured-markdown.json` | Hedge-filled opener, no headings |
| `url-score-wikipedia-rag.json` | Real URL scored: Wikipedia RAG article via Firecrawl |
| `url-score-anthropic-agents.json` | Real URL scored: Anthropic's "Building Effective Agents" blog |
| `score-generated-articles.json` | AEO scores for all articles in `articles/` |

## Fan-out Analysis (`fanout/`)

Decompose a query into 10-15 sub-queries and measure content coverage gaps via Voyage embeddings.

| File | What it shows |
|------|--------------|
| `full-pipeline-crm.json` | End-to-end: LLM generates sub-queries for "best CRM for startups" + Voyage gap analysis against CRM content |
| `full-pipeline-crm.log` | Step trace: generation timing, type counts, coverage %, per-query similarity scores |
| `url-analysis-wikipedia-rag.json` | URL-backed gap analysis: fetch Wikipedia RAG article, generate sub-queries, measure coverage |
| `subqueries-crm.json` | Just the LLM-generated sub-queries (12 queries across 6 types) |
| `crm-url-gap.json` | CLI-generated fan-out with URL content |
| `onboarding-file-gap.json` | CLI-generated fan-out against a local article file |

## CLI Workflows (`article-workflows/` + `jobs/`)

Each topic folder under `article-workflows/` contains the full CLI artifact set: `generate`, `status`, `watch`, `result --summary`, `result --json`, `result` (markdown), and `export`.

See `article-workflows/manifest.tsv` for the slug/job-id/topic mapping.

`jobs/` contains job lifecycle examples: list, status on failed jobs, and resume output.

## Test Artifacts (`_internals/`)

Each module's `_internals/` subdirectory contains granular outputs from E2E tests — individual check scores, parser detection, fetch responses, regex matches, SERP mocks, etc. These are written by `tests/test_*_e2e.py` and are useful for debugging but not for understanding what autoseo produces.
