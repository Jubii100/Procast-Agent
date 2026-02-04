"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================================================
    # Database Configuration
    # ==========================================================================
    database_url: PostgresDsn = Field(
        default="postgresql://postgres:postgres@localhost:5432/procast",
        description="Admin database connection URL",
    )
    database_url_readonly: PostgresDsn = Field(
        default="postgresql://procast_analyst:analyst_readonly@localhost:5432/procast",
        description="Read-only database connection URL for AI agent",
    )
    db_pool_size: int = Field(default=5, ge=1, le=20)
    db_max_overflow: int = Field(default=10, ge=0, le=50)
    db_pool_timeout: int = Field(default=30, ge=5, le=120)

    # ==========================================================================
    # LLM Configuration
    # ==========================================================================
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude",
    )
    llm_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude model identifier",
    )
    llm_max_tokens: int = Field(default=4096, ge=256, le=8192)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_auxiliary_model: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Cheaper model for auxiliary tasks (domain selection, intent classification)",
    )
    llm_cache_enabled: bool = Field(
        default=True,
        description="Enable DSPy request caching for LLM calls",
    )

    # ==========================================================================
    # API Configuration
    # ==========================================================================
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1024, le=65535)
    api_debug: bool = Field(default=True)
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="Comma-separated CORS origins",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # ==========================================================================
    # Authentication (Pre-JWT)
    # ==========================================================================
    mock_user_id: str = Field(
        default="test-user-123",
        description="Mock user ID for local testing",
    )
    mock_user_email: str = Field(
        default="test@procast.local",
        description="Mock user email for local testing",
    )

    # JWT settings
    jwt_secret_key: str = Field(
        default="dev-secret-change-me",
        description="JWT signing secret (override in production)",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_issuer: Optional[str] = Field(
        default=None,
        description="Expected JWT issuer (optional)",
    )
    jwt_audience: Optional[str] = Field(
        default=None,
        description="Expected JWT audience (optional)",
    )

    # ==========================================================================
    # Observability
    # ==========================================================================
    langchain_tracing_v2: bool = Field(default=False)
    langchain_api_key: Optional[str] = Field(default=None)
    langchain_project: str = Field(default="procast-ai")
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper

    # ==========================================================================
    # Agent Configuration
    # ==========================================================================
    max_query_results: int = Field(default=1000, ge=1, le=10000)
    query_timeout_seconds: int = Field(default=30, ge=5, le=120)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    min_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
