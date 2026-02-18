"""
Core Pydantic models for request/response schemas and data models.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# =============================================================================
# Paper Models
# =============================================================================

class Paper(BaseModel):
    """Research paper data model."""
    id: str = Field(..., description="Unique paper identifier")
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(default_factory=list, description="List of authors")
    abstract: str = Field(..., description="Paper abstract")
    year: int = Field(..., description="Publication year")
    keywords: Optional[List[str]] = Field(default=None, description="Paper keywords")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "paper_001",
                "title": "Deep Learning Approaches for NLP",
                "authors": ["Dr. Ahmad Rizky", "Dr. Siti Nurhaliza"],
                "abstract": "This paper explores deep learning techniques...",
                "year": 2023,
                "keywords": ["deep learning", "NLP", "transformers"]
            }
        }


class PaperResult(Paper):
    """Paper with relevance score for search results."""
    relevance_score: float = Field(..., description="Search relevance score")


# =============================================================================
# Search Models
# =============================================================================

class SearchRequest(BaseModel):
    """Paper search request."""
    query: str = Field(..., min_length=1, description="Search query")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum results")
    search_field: str = Field(
        default="all",
        description="Field to search: 'title', 'abstract', 'authors', or 'all'"
    )


class SearchResponse(BaseModel):
    """Paper search response."""
    results: List[PaperResult]
    total: int = Field(..., description="Total matching papers")
    query: str = Field(..., description="Original search query")


# =============================================================================
# Chat Models
# =============================================================================

class ChatRequest(BaseModel):
    """Chat request with optional streaming."""
    question: str = Field(..., min_length=1, description="User question")
    stream: bool = Field(default=True, description="Enable streaming response")
    session_id: Optional[str] = Field(default=None, description="Conversation session ID")
    mode: str = Field(default="basic", description="Chat mode: 'basic' or 'deep'")


class ChatResponse(BaseModel):
    """Non-streaming chat response."""
    answer: str = Field(..., description="Generated answer")
    sources: List[str] = Field(default_factory=list, description="Referenced paper IDs")
    context: Optional[str] = Field(default=None, description="Retrieved context")


class StreamChunk(BaseModel):
    """Streaming response chunk."""
    type: str = Field(..., description="Chunk type: 'token', 'sources', 'done'")
    content: Optional[str] = Field(default=None, description="Chunk content")
    sources: Optional[List[str]] = Field(default=None, description="Source paper IDs")


# =============================================================================
# Health & Status Models
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str
    timestamp: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class APIInfo(BaseModel):
    """API information response."""
    name: str
    version: str
    description: str
    endpoints: dict
