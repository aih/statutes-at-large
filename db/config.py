from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://statutes:statutes@localhost:5434/statutes"

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 2
    db_pool_recycle: int = 1800
    # Per-transaction bounds for API sessions, in milliseconds. Ingest uses
    # `db.base.SessionLocal` directly and keeps an unbounded budget.
    db_statement_timeout_ms: int = 20_000
    db_idle_in_transaction_timeout_ms: int = 30_000

    site_origin: str = "https://statutes.linkedlegislation.org"
    uscode_origin: str = "https://uscode.linkedlegislation.org"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
