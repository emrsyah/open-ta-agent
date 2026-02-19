import logging
import voyageai
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import PaperResult
from app.db.crud import CatalogCRUD
from app.db.models import Catalog
from app.config import get_settings

logger = logging.getLogger(__name__)


class PaperRetriever:
    """
    Search-optimized paper retriever using Voyage AI embeddings and PGVector.
    """
    
    def __init__(self, db_session: Optional[AsyncSession] = None):
        """Initialize retriever."""
        settings = get_settings()
        self.db_session = db_session
        self._crud: Optional[CatalogCRUD] = None
        self._papers_cache: List[PaperResult] = []
        
        # Initialize Voyage AI client
        api_key = settings.VOYAGE_API_KEY
        if api_key:
            self.voyage_client = voyageai.AsyncClient(api_key=api_key)
            self.embedding_model = settings.EMBEDDING_MODEL
            logger.info(f"[RETRIEVER] Voyage AI initialized with model: {self.embedding_model}")
        else:
            self.voyage_client = None
            logger.warning("[RETRIEVER] VOYAGE_API_KEY not set. Vector search will be disabled.")
    
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
            abstract=catalog.abstract or catalog.subject or "No abstract available",
            year=catalog.publication_year or 0,
            keywords=[catalog.catalog_type] if catalog.catalog_type else [],
            relevance_score=relevance_score
        )
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text using Voyage AI."""
        if not self.voyage_client:
            raise ValueError("Voyage AI client not initialized")
        
        # Voyage AI suggests using truncation for long inputs
        result = await self.voyage_client.embed(
            [text],
            model=self.embedding_model,
            input_type="query"  # Crucial for retrieval performance
        )
        return result.embeddings[0]

    async def search(
        self,
        query: str,
        limit: int = 5,
        catalog_type: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        use_vector: bool = True
    ) -> List[PaperResult]:
        """
        Search papers in database. Uses vector search if available.
        
        Args:
            query: Search query
            limit: Maximum results
            catalog_type: Filter by catalog type
            year_from: Filter by minimum year
            year_to: Filter by maximum year
            use_vector: Whether to use semantic vector search
            
        Returns:
            List of papers with relevance scores
        """
        logger.info(f"[RETRIEVER] Searching for: '{query}' (limit={limit}, vector={use_vector})")
        
        if not self._crud:
            return self._search_cache(query, limit)
        
        try:
            if use_vector and self.voyage_client:
                # Semantic Vector Search
                embedding = await self._get_embedding(query)
                results = await self._crud.vector_search(
                    embedding=embedding,
                    limit=limit,
                    catalog_type=catalog_type,
                    year_from=year_from,
                    year_to=year_to
                )
                logger.info(f"[RETRIEVER] Vector search returned {len(results)} results")
            else:
                # Keyword Search Fallback
                results, _ = await self._crud.search(
                    query=query,
                    catalog_type=catalog_type,
                    year_from=year_from,
                    year_to=year_to,
                    limit=limit
                )
                logger.info(f"[RETRIEVER] Keyword search returned {len(results)} results")
                
            return [self._catalog_to_paper(c, score) for c, score in results]
            
        except Exception as e:
            logger.error(f"[RETRIEVER] Search error: {e}", exc_info=True)
            # Fallback to keyword search if vector search fails
            if use_vector:
                return await self.search(query, limit, catalog_type, year_from, year_to, use_vector=False)
            raise
    
    def _search_cache(self, query: str, limit: int) -> List[PaperResult]:
        """Search in cached papers (fallback)."""
        query_lower = query.lower()
        matches = []
        for paper in self._papers_cache:
            if query_lower in paper.title.lower() or query_lower in (paper.abstract or "").lower():
                matches.append(paper)
        return matches[:limit]
    
    async def get_papers_with_context(self, query: str, top_k: int = 3) -> tuple[str, List[PaperResult]]:
        """
        Retrieve papers and return both the formatted context string and the paper objects.
        Use this instead of get_context() so callers can enrich sources without extra DB calls.
        """
        logger.info(f"[RETRIEVER] Context retrieval for: '{query}'")
        papers = await self.search(query, limit=top_k)

        if not papers:
            return "No relevant papers found in the catalog.", []

        context_parts = []
        for i, paper in enumerate(papers, 1):
            context_parts.append(
                f"Paper {i} (ID: {paper.id})\n"
                f"Title: {paper.title}\n"
                f"Authors: {', '.join(paper.authors)}\n"
                f"Year: {paper.year}\n"
                f"Abstract: {paper.abstract}\n"
            )

        return "\n---\n".join(context_parts), papers

    async def get_context(self, query: str, top_k: int = 3) -> str:
        """Get formatted context string for RAG."""
        context, _ = await self.get_papers_with_context(query, top_k)
        return context
    
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
