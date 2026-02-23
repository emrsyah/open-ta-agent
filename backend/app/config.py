"""
Application configuration and settings.
Uses pydantic-settings for environment variable management.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional, List


def parse_cors_origins(v: str) -> List[str]:
    """Parse CORS origins from comma-separated string."""
    if not v:
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5500",
            "http://localhost:5500",
        ]
    return [origin.strip() for origin in v.split(",")]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys (at least one required)
    OPENROUTER_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    VOYAGE_API_KEY: Optional[str] = None
    
    # JWT Authentication (shared secret with Next.js frontend)
    JWT_SECRET: Optional[str] = None,
    JWT_ALGORITHM: str = "HS256",
    JWT_EXPIRATION_MINUTES: int = 5
    
    # OpenRouter Configuration
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # DSPy / LLM Configuration
    # Main model (high quality, for answer generation)
    DSPY_MODEL: str = "openrouter/google/gemini-2.5-flash-lite"
    DSPY_FALLBACK_MODEL: str = "openai/gpt-4o-mini"
    
    # Cheap model (fast/cost-effective, for query generation and simple tasks)
    DSPY_CHEAP_MODEL: str = "openrouter/google/gemini-2.5-flash-lite"
    # Alternative cheap options:
    # - "openrouter/meta-llama/llama-3.2-3b-instruct" (very cheap)
    # - "openrouter/google/gemini-flash-1.5" (fast)
    # - "openrouter/nvidia/llama-3.1-nemotron-70b-instruct:free" (free tier)
    
    DSPY_MAX_WORKERS: int = 4
    
    # Retrieval Configuration
    RETRIEVAL_TOP_K: int = 3
    EMBEDDING_MODEL: str = "voyage-4-lite"
    EMBEDDING_DIM: int = 1024
    
    # Application Configuration
    APP_NAME: str = "Telkom Paper Research API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "AI-powered paper research platform for Telkom University"
    
    # CORS Configuration (comma-separated in .env, e.g., "http://localhost:3000,http://localhost:5173")
    CORS_ORIGINS_STR: Optional[str] = None
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # Data Configuration
    PAPERS_DATA_PATH: str = "data/papers.json"
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Get CORS origins as list."""
        return parse_cors_origins(self.CORS_ORIGINS_STR or "")
    
    # Database Configuration (Supabase PostgreSQL)
    DATABASE_URL: Optional[str] = None
    DATABASE_HOST: Optional[str] = None
    DATABASE_PORT: int = 5432
    DATABASE_NAME: Optional[str] = None
    DATABASE_USER: Optional[str] = None
    DATABASE_PASSWORD: Optional[str] = None
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Database Pool Settings
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"
    
    def get_api_key(self) -> str:
        """Get the primary API key (OpenRouter preferred)."""
        if self.OPENROUTER_API_KEY:
            return self.OPENROUTER_API_KEY
        if self.OPENAI_API_KEY:
            return self.OPENAI_API_KEY
        raise ValueError(
            "No API key configured. Set OPENROUTER_API_KEY or OPENAI_API_KEY."
        )
    
    def is_openrouter(self) -> bool:
        """Check if using OpenRouter."""
        return self.OPENROUTER_API_KEY is not None
    
    def get_database_url(self) -> str:
        """Get database URL (construct from parts if full URL not provided)."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        
        if all([self.DATABASE_HOST, self.DATABASE_NAME, self.DATABASE_USER, self.DATABASE_PASSWORD]):
            return f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        
        raise ValueError(
            "Database not configured. Set DATABASE_URL or all of: "
            "DATABASE_HOST, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD"
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
