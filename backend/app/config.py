from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Postgres
    postgres_user: str = "veritas"
    postgres_password: str = "veritas_secret"
    postgres_db: str = "veritas_db"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Valkey
    valkey_host: str = "valkey"
    valkey_port: int = 6379
    valkey_password: str = ""

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "veritas_policies"

    # JWT
    jwt_secret_key: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # LLM
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_primary_model: str = "gemini/gemini-2.5-flash"
    llm_fallback_model: str = "openai/gpt-4o-mini"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def valkey_url(self) -> str:
        if self.valkey_password:
            return f"redis://:{self.valkey_password}@{self.valkey_host}:{self.valkey_port}/0"
        return f"redis://{self.valkey_host}:{self.valkey_port}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
