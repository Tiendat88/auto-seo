# AutoSEO — AI-Powered SEO & AEO Engine

AutoSEO is a comprehensive backend service and command-line tool suite built for automated SEO-optimized article generation, search visibility analysis (AEO scoring and gap analysis), brand mention monitoring across AI search engines, and real-time auto-publishing webhook integrations. 

The core system is powered by **LiteLLM** (defaulting to DeepSeek/OpenRouter or any OpenAI-compatible gateway) and manages a strict, resilient state-machine pipeline.

---

## 🚀 Key Features

*   **State-Machine Generation Pipeline**: Resilient article drafting pipeline: `RESEARCHING` → `PLANNING` → `GENERATING` → `SCORING` → `REVIEWING` → `EDITING` → `COMPLETED`.
*   **Automatic Webhook Publishing (Auto-Post)**: Expose custom CMS endpoints to securely receive publish-ready articles (structured in HTML, Markdown, meta tags, and FAQ schemas).
*   **Keyword Campaign Decomposition**: Split a main keyword/topic into highly aligned sub-keywords via AI and batch-schedule them into background generation jobs (`run_campaign.py`).
*   **Answer Engine Optimization (AEO)**: Score articles for search engine visibility, extract snippets, and perform semantic gap analysis using VoyageAI embeddings.
*   **Brand Mention Monitor**: Discover, fetch, and analyze brand visibility, positions, and sentiment across top AI search models (ChatGPT, Perplexity, Gemini, Grok) via API and browser automation.
*   **Intelligent Scrubber & Scorer**: Post-process generated articles to clean zero-width unicode spaces, split over-long paragraphs, normalise layouts, and score quality across 13 dimensions (7 algorithmic + 6 LLM).

---

## 🛠️ Technology Stack

*   **Backend Framework**: FastAPI + Typer CLI
*   **LLM Gateway**: LiteLLM (`app/llm.py`) for unified API gateway support (e.g. DeepSeek-Chat, GPT-4o, Claude)
*   **Database**: PostgreSQL with async SQLAlchemy (SQLite for tests)
*   **Caching**: Redis
*   **SERP & Scraping**: SerpAPI + Firecrawl (with fallback mock scraper)
*   **Automated Mentions Fetcher**: Playwright (for AI platform scraping)
*   **Text & NLP**: spaCy (`en_core_web_sm`), textstat, VoyageAI (`voyage-4-large`)
*   **Frontend**: Next.js App Router + TypeScript + Tailwind CSS

---

## 🏃 Quick Start

### 1. Prerequisites
Ensure you have Docker, Python 3.12+, and Node.js installed.

### 2. Start Infrastructure
Run PostgreSQL and Redis in the background:
```bash
docker-compose up -d
```

### 3. Install Backend Dependencies
Sync dependencies and setup resources:
```bash
# Install dependencies using uv (recommended)
uv sync --extra dev --python 3.12

# Download spaCy NLP model (Required for AEO tests and analysis)
uv run python -m spacy download en_core_web_sm

# Install Playwright Chromium (Required for brand monitor browser fetches)
uv run playwright install chromium
```

### 4. Configure Environment
Copy `.env.example` to `.env` and fill in your gateway endpoints/keys:
```bash
cp .env.example .env
```
Ensure you have configured `LITELLM_API_KEY` and `LITELLM_BASE_URL` if you are using a local or external LiteLLM gateway.

### 5. Launch the Services
Start the FastAPI server:
```bash
# Start backend (using 2 workers to prevent event-loop blocks)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

Start the Next.js Frontend:
```bash
cd frontend
pnpm install
pnpm dev
```
Open [http://localhost:3050](http://localhost:3050) in your browser.

---

## 🧬 Core Architecture

### Article Generation Pipeline
The pipeline runs asynchronously inside background tasks. Each step's output is saved to the PostgreSQL database in real-time, allowing resume functionality if a job fails or is interrupted:

```text
               ┌───────────────────────┐
               │    Create Job (POST)  │
               └───────────┬───────────┘
                           ▼
                 [ Step 1: RESEARCH ]   (Mock/SerpAPI + Firecrawl scraping)
                           ▼
                  [ Step 2: PLANNING ]   (Competitor analysis + outlines)
                           ▼
                 [ Step 3: GENERATING ]  (Drafting + SEO meta generation)
                           ▼
                  [ Step 4: SCORING ]    (7 algorithmic + 6 LLM metrics)
                           ▼
                  [ Step 5: REVIEWING ]  (Multi-point editorial check)
                           ▼
                /─── [Is Quality OK?] ───\
               Yes                       No
                │                        │
                ▼                        ▼
           [ COMPLETED ]        [ Step 6: EDITING ] (In-place revisions)
                                         │
                                         └─► Loop back to Scoring (max 10)
```

1. **Research**: Gathers SERP data and main content from competitor URLs.
2. **Planning**: Identifies keywords, user intent, content gaps, and builds an editorial brief. Optional Brand Voice parameters are injected here.
3. **Generating**: Produces the article and FAQ in one call, generates SEO meta-options, and runs the content through the **Scrubber** to fix styling, split long paragraphs, and strip zero-width characters.
4. **Scoring**: Calculates metrics like readability, keyword density, and distribution. Evaluates LLM metrics (accuracy, depth, structure).
5. **Reviewing / Editing**: Fails quality checks lead to targeted re-writes of sections using LLM instructions.

---

## 📄 Auto-Post Webhook Publishing

You can link any website to AutoSEO to receive newly completed articles automatically:
1. In the Web UI, go to **Đăng bài → Nền tảng → Thêm mới**.
2. Input your **Endpoint URL**, a secure **Secret Key**, and default publication status (`draft` / `published`).
3. Turn on **Auto-Publish** to automatically POST to your endpoint when the pipeline completes.

For detailed payloads, response specifications, and code samples (Next.js, Express, Django, Laravel), see [AUTOSEO_INTEGRATION_GUIDE.md](file:///Users/phamtiendat/auto-seo/AUTOSEO_INTEGRATION_GUIDE.md).

---

## 🎯 Campaigns & Keywords Auto-Decomposition

AutoSEO includes a keyword campaign helper to target a broad theme and schedule articles in parallel:

```bash
uv run python run_campaign.py "từ khóa chính của bạn" [số lượng từ khóa phụ]
```

**How it works:**
1. Calls the LiteLLM model to decompose the main topic into a logical map of $N$ specific keywords (e.g. 5-15 sub-topics).
2. Automatically creates and queues jobs in PostgreSQL database for each keyword.
3. You can watch the progress in real-time in the Web UI under `http://localhost:3050/pipeline`.

---

## ⚙️ Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `LITELLM_API_KEY` | — | API key for LiteLLM / OpenAI-compatible endpoint. |
| `LITELLM_MODEL` | `openrouter/deepseek/deepseek-chat` | Model name to pass to your gateway. |
| `LITELLM_BASE_URL` | `http://localhost:4000` | LiteLLM or OpenAI-compatible endpoint URL. |
| `SERP_PROVIDER` | `mock` | `mock` or `serpapi`. |
| `SERPAPI_KEY` | — | API key for SerpAPI (if `serp_provider=serpapi`). |
| `FIRECRAWL_API_KEY` | — | API key for Firecrawl (scrapes top search links). |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis caching URL. |
| `QUALITY_THRESHOLD` | `0.8` | Minimum quality score required to pass. |
| `MAX_REVISIONS` | `10` | Maximum edit iterations allowed before failing. |
| `AEO_SIMILARITY_THRESHOLD` | `0.72` | Embedding matching threshold for gap analysis. |
| `DEBUG` | `false` | Enable SQL query logs. |

---

## 💻 CLI Commands Guide

The `autoseo` project script is built on Typer. Run the following commands:

```bash
# Generate a new article
uv run autoseo generate "best CRM software" --words 1500

# Generate with brand voice guidelines
uv run autoseo generate "best CRM software" --brand-voice brand.json

# Stream real-time pipeline events
uv run autoseo -v generate "topic"

# View status / details of a job
uv run autoseo status <job-id>
uv run autoseo watch <job-id>
uv run autoseo result <job-id> --summary

# Export finished article with JSON-LD metadata
uv run autoseo export <job-id> output.md

# Run AEO assessment on an HTML file
uv run autoseo aeo tests/fixtures/article_good.html

# Run brand visibility analysis
uv run autoseo brand "Notion" "best note-taking app"
```

---

## 🧪 Testing

The repository includes a comprehensive test suite of unit and integration tests.

```bash
# Run unit tests (excludes E2E tests)
uv run pytest tests/ -x -q -k "not e2e"
```

To run E2E integration tests (requires real API credentials/keys):
*   `tests/test_pipeline_e2e.py`
*   `tests/test_brand_e2e.py`
*   `tests/test_aeo_e2e.py`
*   `tests/test_fanout_e2e.py`
