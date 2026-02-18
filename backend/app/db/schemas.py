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
