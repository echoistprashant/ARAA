from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings following 12-factor principles."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Autonomous Research & Analysis Agent (ARAA)"
    APP_ENV: Literal["local", "staging", "production"] = "local"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Datastores
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://araa_user:araa_password@localhost:5432/araa_db"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # LLM Provider Configuration
    LLM_PROVIDER: Literal["gemini", "groq", "ollama", "openai"] = "gemini"
    GEMINI_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: str | None = None

    # Model identifiers
    PLANNER_MODEL: str = "gemini-flash-lite-latest"
    ACTOR_MODEL: str = "gemini-flash-lite-latest"
    VERIFIER_MODEL: str = "gemini-flash-lite-latest"

    # Search Provider
    SEARCH_PROVIDER: Literal["duckduckgo", "tavily", "brave"] = "duckduckgo"
    TAVILY_API_KEY: str | None = None

    # Agent Limits & Budgets
    MAX_STEPS_DEFAULT: int = 25
    MAX_COST_USD_DEFAULT: float = 1.50
    RUN_TIMEOUT_S: int = 600

    # Security & Execution Sandbox
    JWT_SECRET: str = "change-in-production-long-random-string"
    SANDBOX_IMAGE: str = "python:3.12-slim"


settings = Settings()
