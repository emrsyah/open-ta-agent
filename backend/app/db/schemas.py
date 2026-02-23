"""
Pydantic schemas for API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CatalogBase(BaseModel):
    """Base catalog schema with common fields."""
    title: str
    catalog_number: Optional[str] = None
    catalog_type: Optional[str] = None
    classification_number: Optional[str] = None
    subject: Optional[str] = None
    author: Optional[str] = None
    editor: Optional[str] = None
    publisher: Optional[str] = None
    shelf_number: Optional[str] = None
    library_location: Optional[str] = None
    publication_year: Optional[int] = None
    total_copies: int = 0
    access_link: Optional[str] = None


class CatalogCreate(CatalogBase):
    """Schema for creating a new catalog entry."""
    pass


class CatalogUpdate(BaseModel):
    """Schema for updating a catalog entry (all fields optional)."""
    title: Optional[str] = None
    catalog_number: Optional[str] = None
    catalog_type: Optional[str] = None
    classification_number: Optional[str] = None
    subject: Optional[str] = None
    author: Optional[str] = None
    editor: Optional[str] = None
    publisher: Optional[str] = None
    shelf_number: Optional[str] = None
    library_location: Optional[str] = None
    publication_year: Optional[int] = None
    total_copies: Optional[int] = None
    access_link: Optional[str] = None


class CatalogResponse(CatalogBase):
    """Schema for catalog API responses."""
    id: int
    
    class Config:
        from_attributes = True  # Enable ORM mode for SQLAlchemy models


class CatalogListResponse(BaseModel):
    """Schema for list of catalogs with pagination."""
    items: List[CatalogResponse]
    total: int
    page: int
    page_size: int
    pages: int


# User schemas
class UserBase(BaseModel):
    """Base user schema with common fields."""
    name: str
    email: str
    email_verified: bool = False
    image: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user (includes password)."""
    password: str = Field(..., min_length=8, max_length=100)


class UserUpdate(BaseModel):
    """Schema for updating user information (all fields optional)."""
    name: Optional[str] = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    image: Optional[str] = None


class UserResponse(UserBase):
    """Schema for user API responses."""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Verification schemas
class VerificationBase(BaseModel):
    """Base verification schema with common fields."""
    identifier: str
    value: str
    expires_at: datetime


class VerificationCreate(VerificationBase):
    """Schema for creating a new verification token."""
    id: Optional[str] = None


class VerificationResponse(VerificationBase):
    """Schema for verification API responses."""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Rate limit schemas
class RateLimitBase(BaseModel):
    """Base rate limit schema with common fields."""
    key: str
    count: int
    last_request: int


class RateLimitResponse(RateLimitBase):
    """Schema for rate limit API responses."""
    id: str

    class Config:
        from_attributes = True

# Search-specific schemas
class CatalogSearchRequest(BaseModel):
    """Request schema for searching catalogs."""
    query: str = Field(..., min_length=1, description="Search query string")
    search_fields: List[str] = Field(
        default=["title", "author", "subject"],
        description="Fields to search in"
    )
    catalog_type: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class CatalogSearchResult(BaseModel):
    """Single search result with relevance score."""
    catalog: CatalogResponse
    relevance_score: float = Field(..., description="Search relevance score")


class CatalogSearchResponse(BaseModel):
    """Response schema for catalog search."""
    results: List[CatalogSearchResult]
    total: int
    query: str
    search_time_ms: float


# Filter schemas
class CatalogFilterRequest(BaseModel):
    """Request schema for filtering catalogs."""
    catalog_type: Optional[str] = None
    publication_year: Optional[int] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    library_location: Optional[str] = None
    has_electronic_access: Optional[bool] = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(default="publication_year", pattern="^(title|publication_year|author|id)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")



# Conversation and Message schemas
class MessageBase(BaseModel):
    """Base message schema with common fields."""
    question: str
    answer: str
    sources: Optional[list] = None
    search_query: Optional[str] = None


class MessageCreate(MessageBase):
    """Schema for creating a new message."""
    conversation_id: str


class MessageResponse(MessageBase):
    """Schema for message API responses."""
    id: int
    conversation_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationBase(BaseModel):
    """Base conversation schema with common fields."""
    title: Optional[str] = None
    is_incognito: bool = False
    user_id: Optional[str] = None


class ConversationCreate(ConversationBase):
    """Schema for creating a new conversation."""
    id: Optional[str] = None


class ConversationUpdate(BaseModel):
    """Schema for updating conversation (all fields optional)."""
    title: Optional[str] = None
    is_incognito: Optional[bool] = None


class ConversationResponse(ConversationBase):
    """Schema for conversation API responses."""
    id: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """Schema for list of conversations with pagination."""
    items: List[ConversationResponse]
    total: int
    page: int
    page_size: int
    pages: int