from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://postgres@localhost"
        "/secondloop"
    )
    parcelpath_url: str = "http://localhost:8081"
    parcelpath_timeout_s: float = 5.0


settings = Settings()
