"""
Paper retriever service for searching and retrieving papers from database.
Uses PostgreSQL with SQLAlchemy for async queries.
"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import PaperResult
from app.db.crud import CatalogCRUD
from app.db.models import Catalog


class PaperRetriever:
    """
    Database-backed paper retriever using PostgreSQL.
    
    Replaces the mock data with real catalog data from Supabase.
    Supports keyword search with relevance scoring.
    
    TODO: Add vector search implementation:
    - dspy.retrievers.Embeddings for semantic search
    - Hybrid approach: BM25 on title + vector on abstract
    """
    
    def __init__(self, db_session: Optional[AsyncSession] = None):
        """
        Initialize retriever.
        
        Args:
            db_session: Async database session (can be set later)
        """
        self.db_session = db_session
        self._crud: Optional[CatalogCRUD] = None
        self._papers_cache: List[PaperResult] = []
    
    def set_session(self, db_session: AsyncSession):
        """Set the database session (called during app startup)."""
        self.db_session = db_session
        self._crud = CatalogCRUD(db_session)
    
    def _catalog_to_paper(self, catalog: Catalog, relevance_score: float = 0.0) -> PaperResult:
        """Convert database Catalog model to PaperResult API model."""
        return PaperResult(
            id=f"catalog_{catalog.id}",
            title=catalog.title,
            authors=catalog.author.split(", ") if catalog.author else ["Unknown"],
            abstract=catalog.subject or "No abstract available",
            year=catalog.publication_year or 0,
            keywords=[catalog.catalog_type] if catalog.catalog_type else [],
            relevance_score=relevance_score
        )
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        search_field: str = "all",
        catalog_type: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None
    ) -> List[PaperResult]:
        """
        Search papers in database by keyword.
        
        Args:
            query: Search query
            limit: Maximum results
            search_field: Which field to search ('all', 'title', 'subject', 'author')
            catalog_type: Filter by catalog type
            year_from: Filter by minimum year
            year_to: Filter by maximum year
            
        Returns:
            List of papers with relevance scores
        """
        if not self._crud:
            # Fallback to cache if no database
            return self._search_cache(query, limit)
        
        # Map search fields
        field_mapping = {
            "all": ["title", "author", "subject"],
            "title": ["title"],
            "abstract": ["subject"],  # Drizzle schema uses 'subject' not 'abstract'
            "authors": ["author"],
            "subject": ["subject"],
        }
        search_fields = field_mapping.get(search_field, field_mapping["all"])
        
        # Query database
        results, _ = await self._crud.search(
            query=query,
            search_fields=search_fields,
            catalog_type=catalog_type,
            year_from=year_from,
            year_to=year_to,
            limit=limit,
            offset=0
        )
        
        # Convert to PaperResult
        papers = []
        for catalog, score in results:
            paper = self._catalog_to_paper(catalog, relevance_score=score)
            papers.append(paper)
        
        return papers
    
    def _search_cache(self, query: str, limit: int) -> List[PaperResult]:
        """Search in cached papers (fallback when DB unavailable)."""
        query_lower = query.lower()
        query_words = query_lower.split()
        matches = []
        
        for paper in self._papers_cache:
            score = 0
            title_lower = paper.title.lower()
            
            if any(word in title_lower for word in query_words):
                score += 3
            if query_lower in title_lower:
                score += 5
            
            if score > 0:
                paper_dict = paper.model_dump()
                paper_dict["relevance_score"] = score
                matches.append((score, PaperResult(**paper_dict)))
        
        matches.sort(key=lambda x: x[0], reverse=True)
        return [paper for _, paper in matches[:limit]]
    
    async def get_context(self, query: str, top_k: int = 3) -> str:
        """
        Get formatted context string for RAG.
        
        Args:
            query: Search query
            top_k: Number of papers to include
            
        Returns:
            Formatted context string
        """
        papers = await self.search(query, limit=top_k)
        
        if not papers:
            return "No relevant papers found in the catalog."
        
        context_parts = []
        for i, paper in enumerate(papers, 1):
            context_parts.append(
                f"Paper {i} (ID: {paper.id}):\n"
                f"Title: {paper.title}\n"
                f"Authors: {', '.join(paper.authors)}\n"
                f"Year: {paper.year}\n"
                f"Abstract: {paper.abstract}\n"
            )
        
        return "\n---\n".join(context_parts)
    
    async def get_all_papers(self, limit: int = 100) -> List[PaperResult]:
        """Return all papers from database."""
        if not self._crud:
            return self._papers_cache
        
        catalogs, _ = await self._crud.get_all(limit=limit, offset=0)
        return [self._catalog_to_paper(c) for c in catalogs]
    
    async def get_paper_by_id(self, paper_id: str) -> Optional[PaperResult]:
        """Get a single paper by ID."""
        # Extract numeric ID from "catalog_X"
        try:
            catalog_id = int(paper_id.replace("catalog_", ""))
        except ValueError:
            return None
        
        if not self._crud:
            # Search in cache
            for paper in self._papers_cache:
                if paper.id == paper_id:
                    return paper
            return None
        
        catalog = await self._crud.get_by_id(catalog_id)
        if catalog:
            return self._catalog_to_paper(catalog)
        return None
    
    async def get_by_catalog_type(
        self, 
        catalog_type: str, 
        limit: int = 100
    ) -> List[PaperResult]:
        """Get papers by catalog type (e.g., 'skripsi', 'ePoster')."""
        if not self._crud:
            return []
        
        catalogs = await self._crud.get_by_catalog_type(catalog_type, limit)
        return [self._catalog_to_paper(c) for c in catalogs]
    
    async def get_by_year(self, year: int, limit: int = 100) -> List[PaperResult]:
        """Get papers from a specific publication year."""
        if not self._crud:
            return []
        
        catalogs = await self._crud.get_recent_by_year(year, limit)
        return [self._catalog_to_paper(c) for c in catalogs]
