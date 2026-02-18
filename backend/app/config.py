"""
Application configuration and settings.
Uses pydantic-settings for environment variable management.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys (at least one required)
    OPENROUTER_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    
    # OpenRouter Configuration
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # DSPy / LLM Configuration
    DSPY_MODEL: str = "openrouter/google/gemini-2.5-pro-preview"
    DSPY_FALLBACK_MODEL: str = "openai/gpt-4o-mini"
    DSPY_MAX_WORKERS: int = 4
    
    # Retrieval Configuration
    RETRIEVAL_TOP_K: int = 3
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_DIM: int = 512
    
    # Application Configuration
    APP_NAME: str = "Telkom Paper Research API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "AI-powered paper research platform for Telkom University"
    
    # CORS Configuration
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ]
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # Data Configuration
    PAPERS_DATA_PATH: str = "data/papers.json"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
    
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


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
