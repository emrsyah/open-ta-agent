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

class ConversationMessage(BaseModel):
    """Single message in conversation history."""
    question: str = Field(..., description="User question")
    answer: str = Field(..., description="Assistant answer")
    sources: Optional[List[str]] = Field(default=None, description="Referenced paper IDs")
    context: Optional[str] = Field(default=None, description="Retrieved context used")


class ChatMetaParams(BaseModel):
    """Metadata parameters for chat request."""
    mode: str = Field(
        default="basic", 
        description="Chat mode: 'basic' or 'deep'"
    )
    stream: bool = Field(
        default=True, 
        description="Enable streaming response via SSE"
    )
    attachments: List[str] = Field(
        default_factory=list,
        description="File attachments (URLs or IDs) - for future use"
    )
    is_incognito: bool = Field(
        default=False,
        description="If true, conversation won't be saved to history"
    )
    timezone: str = Field(
        default="UTC",
        description="User's timezone (e.g., 'Asia/Jakarta', 'America/New_York')"
    )
    language: str = Field(
        default="en-US",
        description="Preferred language code (e.g., 'id-ID', 'en-US')"
    )
    source_preference: str = Field(
        default="all",
        description="Source filter: 'all', 'only_papers', 'only_general'"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Conversation ID for retrieving history"
    )


class ChatRequest(BaseModel):
    """Chat request with query and metadata parameters."""
    query: str = Field(..., min_length=1, description="User's question or message")
    meta_params: ChatMetaParams = Field(
        default_factory=ChatMetaParams,
        description="Metadata parameters for the chat request"
    )
    
    # Backwards compatibility - deprecated fields
    question: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] Use 'query' instead"
    )
    stream: Optional[bool] = Field(
        default=None,
        description="[DEPRECATED] Use 'meta_params.stream' instead"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] Use 'meta_params.conversation_id' instead"
    )
    mode: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] Use 'meta_params.mode' instead"
    )
    
    def get_query(self) -> str:
        """Get query with backwards compatibility."""
        return self.query or self.question or ""
    
    def get_stream(self) -> bool:
        """Get stream preference with backwards compatibility."""
        if self.stream is not None:
            return self.stream
        return self.meta_params.stream
    
    def get_conversation_id(self) -> Optional[str]:
        """Get conversation ID with backwards compatibility."""
        return self.meta_params.conversation_id or self.session_id
    
    def get_mode(self) -> str:
        """Get mode with backwards compatibility."""
        if self.mode is not None:
            return self.mode
        return self.meta_params.mode


class CitedPaper(BaseModel):
    """Full metadata for a paper cited in the answer."""
    id: str = Field(..., description="Paper ID")
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(default_factory=list, description="List of authors")
    abstract: str = Field(..., description="Paper abstract")
    year: int = Field(..., description="Publication year")
    citation_number: int = Field(..., description="Inline citation number used in answer, e.g. [1]")


class ChatResponse(BaseModel):
    """Non-streaming chat response."""
    answer: str = Field(..., description="Generated answer with inline citations like [1], [2]")
    sources: List[CitedPaper] = Field(default_factory=list, description="Cited papers in citation order")
    context: Optional[str] = Field(default=None, description="Retrieved context")
    search_query: Optional[str] = Field(default=None, description="Generated search query used for retrieval")


class StreamChunk(BaseModel):
    """
    Streaming response chunk for SSE events.
    
    Chunk Types:
    - 'start': Stream initialization with metadata
    - 'token': Individual text token from LLM
    - 'rationale': Chain-of-thought reasoning (optional)
    - 'done': Final answer with sources
    - 'metadata': Stream statistics (token count, duration)
    - 'error': Error during streaming
    """
    type: str = Field(
        ..., 
        description="Chunk type: 'start', 'token', 'rationale', 'done', 'metadata', 'error'"
    )
    content: Optional[str] = Field(default=None, description="Chunk content")
    sources: Optional[List[CitedPaper]] = Field(default=None, description="Cited papers with full metadata")
    token_count: Optional[int] = Field(default=None, description="Total tokens streamed")
    duration_ms: Optional[int] = Field(default=None, description="Stream duration in ms")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")
    language: Optional[str] = Field(default=None, description="Response language")


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
