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

    # SEO Lifecycle (continuous research → optimize → measure → refresh loop)
    lifecycle_enabled: bool = False              # master switch: scheduler loop runs only when True
    lifecycle_poll_interval_seconds: int = 300   # leader loop poll cadence
    lifecycle_batch_size: int = 20               # max lifecycles advanced per tick
    lifecycle_max_concurrent: int = 2            # cap on simultaneous SDK-blocking spawns
    lifecycle_default_cadence_days: int = 30     # default re-measure cadence (days)
    lifecycle_rank_threshold: int = 3            # SERP rank worse than this → decay
    lifecycle_aeo_threshold: int = 65            # AEO score below this → decay
    lifecycle_brand_threshold: float = 50.0      # brand visibility below this → decay
    lifecycle_max_content_age_days: int = 90     # hard content-age cap → forced refresh

    # App
    debug: bool = False
    persist_events: bool = False
    cors_origins: str = "http://localhost:3000"


settings = Settings()
