"""
Health check and API info routes.
"""

from fastapi import APIRouter
from datetime import datetime
from app.config import get_settings
from app.core.models import HealthResponse, APIInfo

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns API status and version information.
    
    **Example:**
    ```bash
    curl http://localhost:8000/health
    ```
    """
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        timestamp=datetime.utcnow()
    )


@router.get("/", response_model=APIInfo)
async def api_info():
    """
    API information and available endpoints.
    
    **Example:**
    ```bash
    curl http://localhost:8000/
    ```
    """
    settings = get_settings()
    
    return APIInfo(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
        endpoints={
            "GET /health": "Health check",
            "GET /papers/search": "Search papers by keyword",
            "POST /papers/search": "Search papers (POST)",
            "GET /papers/list": "List all papers",
            "POST /chat/basic": "AI chat with papers (streaming)",
            "POST /chat/deep": "Deep research with RLM (not implemented)"
        }
    )
