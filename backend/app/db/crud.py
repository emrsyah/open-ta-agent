"""
CRUD operations for Catalog model.
"""

import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, text, case
from sqlalchemy.orm import selectinload

from app.db.models import Catalog, CatalogType
from app.db.schemas import CatalogCreate, CatalogUpdate, CatalogFilterRequest

logger = logging.getLogger(__name__)


class CatalogCRUD:
    """CRUD operations for catalog items."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, catalog_id: int) -> Optional[Catalog]:
        """Get a single catalog by ID."""
        result = await self.session.execute(
            select(Catalog).where(Catalog.id == catalog_id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(
        self, 
        limit: int = 10, 
        offset: int = 0,
        order_by: str = "id",
        order_desc: bool = False
    ) -> tuple[List[Catalog], int]:
        """Get all catalogs with pagination. Returns (items, total_count)."""
        # Get total count
        count_result = await self.session.execute(select(func.count(Catalog.id)))
        total = count_result.scalar()
        
        # Build query
        query = select(Catalog)
        
        # Apply ordering
        order_column = getattr(Catalog, order_by, Catalog.id)
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        items = result.scalars().all()
        
        return list(items), total
    
    async def create(self, data: CatalogCreate) -> Catalog:
        """Create a new catalog entry."""
        # Convert catalog_type string to enum if provided
        catalog_type = None
        if data.catalog_type:
            try:
                catalog_type = CatalogType(data.catalog_type)
            except ValueError:
                pass
        
        catalog = Catalog(
            title=data.title,
            catalog_number=data.catalog_number,
            catalog_type=catalog_type,
            classification_number=data.classification_number,
            subject=data.subject,
            author=data.author,
            editor=data.editor,
            publisher=data.publisher,
            shelf_number=data.shelf_number,
            library_location=data.library_location,
            publication_year=data.publication_year,
            total_copies=data.total_copies,
            access_link=data.access_link,
        )
        
        self.session.add(catalog)
        await self.session.commit()
        await self.session.refresh(catalog)
        return catalog
    
    async def update(self, catalog_id: int, data: CatalogUpdate) -> Optional[Catalog]:
        """Update an existing catalog entry."""
        catalog = await self.get_by_id(catalog_id)
        if not catalog:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        
        # Handle catalog_type conversion
        if 'catalog_type' in update_data and update_data['catalog_type']:
            try:
                update_data['catalog_type'] = CatalogType(update_data['catalog_type'])
            except ValueError:
                update_data['catalog_type'] = None
        
        for field, value in update_data.items():
            setattr(catalog, field, value)
        
        await self.session.commit()
        await self.session.refresh(catalog)
        return catalog
    
    async def delete(self, catalog_id: int) -> bool:
        """Delete a catalog entry. Returns True if deleted, False if not found."""
        catalog = await self.get_by_id(catalog_id)
        if not catalog:
            return False
        
        await self.session.delete(catalog)
        await self.session.commit()
        return True
    
    async def search(
        self,
        query: str,
        search_fields: List[str] = None,
        catalog_type: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        limit: int = 10,
        offset: int = 0
    ) -> tuple[List[tuple[Catalog, float]], int]:
        """
        Search catalogs with relevance scoring.
        Returns list of (catalog, score) tuples and total count.
        """
        if search_fields is None:
            search_fields = ["title", "author", "subject"]
        
        # Build search conditions
        search_conditions = []
        query_lower = f"%{query.lower()}%"
        
        field_mapping = {
            "title": Catalog.title,
            "author": Catalog.author,
            "subject": Catalog.subject,
            "publisher": Catalog.publisher,
            "editor": Catalog.editor,
        }
        
        for field in search_fields:
            if field in field_mapping:
                search_conditions.append(
                    func.lower(field_mapping[field]).like(query_lower)
                )
        
        logger.info(f"[CRUD] Search params: query='{query}', fields={search_fields}, limit={limit}")
        logger.debug(f"[CRUD] Search conditions: {len(search_conditions)} conditions, query_lower='{query_lower}'")
        
        # Build base query
        base_query = select(Catalog)
        
        if search_conditions:
            base_query = base_query.where(or_(*search_conditions))
            logger.debug(f"[CRUD] Added search conditions to query")
        
        # Add filters
        filters = []
        
        if catalog_type:
            try:
                cat_type_enum = CatalogType(catalog_type)
                filters.append(Catalog.catalog_type == cat_type_enum)
                logger.debug(f"[CRUD] Added catalog_type filter: {catalog_type}")
            except ValueError:
                logger.warning(f"[CRUD] Invalid catalog_type: {catalog_type}")
                pass
        
        if year_from is not None:
            filters.append(Catalog.publication_year >= year_from)
        
        if year_to is not None:
            filters.append(Catalog.publication_year <= year_to)
        
        if filters:
            base_query = base_query.where(and_(*filters))
        
        # Get total count - count from the subquery
        count_query = select(func.count()).select_from(base_query.subquery())
        logger.debug(f"[CRUD] Executing count query...")
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        logger.info(f"[CRUD] Total matching records: {total}")
        
        # Calculate relevance score using full-text search ranking
        # Higher score if match in title, then author, then subject
        score_expr = func.coalesce(
            case(
                (func.lower(Catalog.title).like(query_lower), 3.0),
                else_=0.0
            ), 0.0
        ) + func.coalesce(
            case(
                (func.lower(Catalog.author).like(query_lower), 2.0),
                else_=0.0
            ), 0.0
        ) + func.coalesce(
            case(
                (func.lower(Catalog.subject).like(query_lower), 1.0),
                else_=0.0
            ), 0.0
        )
        
        # Build final query with scoring
        query_with_score = base_query.add_columns(score_expr.label("score"))
        query_with_score = query_with_score.order_by(score_expr.desc(), Catalog.id.desc())
        query_with_score = query_with_score.offset(offset).limit(limit)
        
        logger.debug(f"[CRUD] Executing final query with scoring...")
        result = await self.session.execute(query_with_score)
        rows = result.all()
        logger.info(f"[CRUD] Query returned {len(rows)} rows")
        
        for i, row in enumerate(rows[:3]):  # Log first 3 results
            catalog = row[0]
            score = row[1]
            logger.debug(f"[CRUD] Result {i+1}: '{catalog.title}' (score: {score})")
        
        return [(row[0], float(row[1])) for row in rows], total
    
    async def filter_catalogs(
        self,
        filters: CatalogFilterRequest
    ) -> tuple[List[Catalog], int]:
        """Filter catalogs based on various criteria."""
        query = select(Catalog)
        
        # Build filter conditions
        conditions = []
        
        if filters.catalog_type:
            try:
                cat_type_enum = CatalogType(filters.catalog_type)
                conditions.append(Catalog.catalog_type == cat_type_enum)
            except ValueError:
                pass
        
        if filters.publication_year:
            conditions.append(Catalog.publication_year == filters.publication_year)
        
        if filters.author:
            conditions.append(
                func.lower(Catalog.author).like(f"%{filters.author.lower()}%")
            )
        
        if filters.subject:
            conditions.append(
                func.lower(Catalog.subject).like(f"%{filters.subject.lower()}%")
            )
        
        if filters.library_location:
            conditions.append(
                func.lower(Catalog.library_location).like(f"%{filters.library_location.lower()}%")
            )
        
        if filters.has_electronic_access is not None:
            if filters.has_electronic_access:
                conditions.append(Catalog.access_link.isnot(None))
            else:
                conditions.append(Catalog.access_link.is_(None))
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Get total count
        count_query = select(func.count(Catalog.id)).select_from(query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar()
        
        # Apply ordering
        order_column = getattr(Catalog, filters.sort_by, Catalog.id)
        if filters.sort_order == "desc":
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())
        
        # Apply pagination
        query = query.offset(filters.offset).limit(filters.limit)
        
        result = await self.session.execute(query)
        items = result.scalars().all()
        
        return list(items), total
    
    async def get_by_catalog_type(self, catalog_type: str, limit: int = 100) -> List[Catalog]:
        """Get all catalogs of a specific type."""
        try:
            cat_type_enum = CatalogType(catalog_type)
        except ValueError:
            return []
        
        result = await self.session.execute(
            select(Catalog)
            .where(Catalog.catalog_type == cat_type_enum)
            .order_by(Catalog.publication_year.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_recent_by_year(self, year: int, limit: int = 100) -> List[Catalog]:
        """Get catalogs from a specific year."""
        result = await self.session.execute(
            select(Catalog)
            .where(Catalog.publication_year == year)
            .order_by(Catalog.title)
            .limit(limit)
        )
        return list(result.scalars().all())
