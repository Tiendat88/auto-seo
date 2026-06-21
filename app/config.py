from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    litellm_api_key: str = ""
    litellm_model: str = "openrouter/deepseek/deepseek-chat"
    litellm_base_url: str = ""

    # SERP
    serp_provider: str = "mock"
    firecrawl_api_key: str | None = None
    webhook_url: str | None = None
    serpapi_key: str = ""
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

    # Brand Monitor
    brand_monitor_max_prompts: int = 14
    brand_monitor_batch_size: int = 3

    # App
    debug: bool = False
    persist_events: bool = False
    cors_origins: str = "http://localhost:3000"


settings = Settings()
