from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://postgres@localhost"
        "/secondloop"
    )
    db_pool_size: int = 10
    db_pool_timeout_s: float = 1.0
    mailer_url: str = "http://localhost:8082"
    parcelpath_url: str = "http://localhost:8081"
    parcelpath_timeout_s: float = 5.0
    # The storefront waits 2 s for a whole quote.
    parcelpath_budget_s: float = 1.0
    parcelpath_breaker_failures: int = 5
    parcelpath_breaker_reset_s: float = 10.0


settings = Settings()
