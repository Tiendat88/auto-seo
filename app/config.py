from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    google_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"
    openai_api_key: str = ""
    openai_model: str = "o3-mini"
    openai_codex: bool = False
    perplexity_api_key: str = ""

    # SERP
    serp_provider: str = "mock"
    serpapi_key: str = ""
    firecrawl_api_key: str = ""
    content_fetch_top_n: int = 10

    # Database
    database_url: str = "postgresql+asyncpg://seo:seo@localhost:5432/seo_agent"

    # Cache
    redis_url: str = "redis://localhost:6379/0"

    # Quality
    quality_threshold: float = 0.8
    max_revisions: int = 10

    # AEO
    aeo_similarity_threshold: float = 0.72
    voyage_api_key: str = ""
    voyage_embedding_model: str = "voyage-4-large"

    # App
    debug: bool = False
    persist_events: bool = False


settings = Settings()
