from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://postgres@localhost"
        "/secondloop"
    )
    db_pool_size: int = 10
    db_pool_timeout_s: float = 1.0
    mailer_url: str = "http://localhost:8082"
    mailer_timeout_s: float = 2.0
    # Shutdown (chapter 14): stay up but not ready for
    # drain_s, then finish requests for at most
    # shutdown_timeout_s. Together they must fit in the
    # platform's grace period (10 s for docker stop).
    drain_s: float = 2.0
    shutdown_timeout_s: float = 5.0
    # How often the worker looks for emails to send.
    worker_poll_s: float = 1.0
    # How long a worker may hold a message (chapter 13).
    outbox_lease_s: float = 30.0
    outbox_max_attempts: int = 10
    parcelpath_url: str = "http://localhost:8081"
    parcelpath_timeout_s: float = 5.0
    # The storefront waits 2 s for a whole quote.
    parcelpath_budget_s: float = 1.0
    parcelpath_breaker_failures: int = 5
    parcelpath_breaker_reset_s: float = 10.0


settings = Settings()
