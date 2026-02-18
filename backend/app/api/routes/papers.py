"""
Paper search and listing API routes.
"""

from fastapi import APIRouter, Query
from typing import List
from app.core.models import (
    SearchRequest, 
    SearchResponse, 
    Paper,
    PaperResult
)
from app.services.rag import get_rag_service

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("/search", response_model=SearchResponse)
async def search_papers_get(
    query: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=5, ge=1, le=20, description="Maximum results"),
    search_field: str = Query(
        default="all",
        description="Field to search: 'all', 'title', 'abstract', or 'authors'"
    )
):
    """
    Search papers by keyword (GET method).
    
    **Example:**
    ```bash
    curl "http://localhost:8000/papers/search?query=machine+learning&limit=5"
    ```
    """
    rag_service = get_rag_service()
    retriever = rag_service.get_retriever()
    
    results = retriever.search(
        query=query,
        limit=limit,
        search_field=search_field
    )
    
    return SearchResponse(
        results=results,
        total=len(results),
        query=query
    )


@router.post("/search", response_model=SearchResponse)
async def search_papers_post(request: SearchRequest):
    """
    Search papers by keyword (POST method).
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/papers/search \\
      -H "Content-Type: application/json" \\
      -d '{"query": "machine learning", "limit": 5}'
    ```
    """
    return await search_papers_get(
        query=request.query,
        limit=request.limit,
        search_field=request.search_field
    )


@router.get("/list", response_model=List[Paper])
async def list_all_papers():
    """
    List all available papers.
    
    **Example:**
    ```bash
    curl http://localhost:8000/papers/list
    ```
    """
    rag_service = get_rag_service()
    retriever = rag_service.get_retriever()
    
    return retriever.get_all_papers()


@router.get("/list", response_model=List[Paper])
async def list_papers():
    """Alias for /list - List all papers."""
    return await list_all_papers()
