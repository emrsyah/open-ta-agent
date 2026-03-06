"""
Filter extraction module for natural language query understanding.

This module provides DSPy signatures and modules for extracting structured
filter parameters from natural language user queries.
"""

import dspy
from typing import Optional


class FilterExtractionSignature(dspy.Signature):
    """
    Extract structured filter parameters from a natural language user query.
    
    Analyze the user's question and identify any filtering criteria they may have
    mentioned implicitly or explicitly. Return structured filter values that can
    be used to narrow down paper search results.
    
    Guidelines:
    - year_from: Extract if user mentions "after 2020", "from 2020", "2020 onwards", "recent papers"
    - year_to: Extract if user mentions "before 2020", "until 2020", "up to 2020"
    - catalog_type: Map user-friendly names to database values
      * "thesis" or "S2" -> "Karya Ilmiah - Thesis (S2) - Reference"
      * "skripsi" or "S1" -> "Karya Ilmiah - Skripsi (S1) - Reference"
      * "disertasi" or "S3" -> "Karya Ilmiah - Disertasi (S3) - Reference"
      * "jurnal internasional" -> "Jurnal Internasional - Reference"
      * "jurnal nasional" -> "Jurnal Nasional - Reference"
      * "e-book" or "ebook" -> "Buku - Elektronik (E-Book)"
      * "proceeding" or "konferensi" -> "Proceeding (Electronic)"
    - author: Extract if user mentions "by [name]", "author [name]", "written by"
    - has_electronic_access: Set to True if user asks for "online", "download", "PDF", "electronic"
    """
    
    question: str = dspy.InputField(desc="The user's natural language question")
    
    year_from: Optional[int] = dspy.OutputField(desc="Minimum publication year (e.g., 2020) or None")
    year_to: Optional[int] = dspy.OutputField(desc="Maximum publication year (e.g., 2024) or None")
    catalog_type: Optional[str] = dspy.OutputField(desc="Catalog type filter or None")
    author: Optional[str] = dspy.OutputField(desc="Author name filter or None")
    has_electronic_access: Optional[bool] = dspy.OutputField(desc="True if only electronic access requested, else None")


class FilterExtractor(dspy.Module):
    """
    DSPy module for extracting filter parameters from user queries.
    
    Uses LLM to understand natural language filtering intent and convert
    it to structured filter parameters for the retrieval system.
    """
    
    def __init__(self):
        super().__init__()
        self.extract = dspy.Predict(FilterExtractionSignature)
    
    def forward(self, question: str) -> dspy.Prediction:
        """
        Extract filter parameters from user question.
        
        Args:
            question: User's natural language question
            
        Returns:
            Prediction with extracted filter fields
        """
        result = self.extract(question=question)
        
        # Clean up and normalize results
        year_from = getattr(result, 'year_from', None)
        year_to = getattr(result, 'year_to', None)
        catalog_type = getattr(result, 'catalog_type', None)
        author = getattr(result, 'author', None)
        has_electronic_access = getattr(result, 'has_electronic_access', None)
        
        # Normalize catalog type using alias mapping
        if catalog_type:
            catalog_type = self._normalize_catalog_type(catalog_type)
        
        # Handle "recent" years
        if year_from == -1 or year_from == 0:
            # "Recent" typically means last 5 years
            import datetime
            year_from = datetime.datetime.now().year - 5
        
        return dspy.Prediction(
            year_from=year_from,
            year_to=year_to,
            catalog_type=catalog_type,
            author=author,
            has_electronic_access=has_electronic_access,
        )
    
    def _normalize_catalog_type(self, user_type: str) -> Optional[str]:
        """
        Normalize user-friendly catalog type names to database values.
        
        Args:
            user_type: User-provided catalog type name
            
        Returns:
            Normalized catalog type name for database query
        """
        from app.services.catalog_types import CATALOG_TYPE_ALIASES
        
        user_type_lower = user_type.lower().strip()
        
        # Check aliases
        for alias, db_value in CATALOG_TYPE_ALIASES.items():
            if alias in user_type_lower:
                return db_value
        
        # Return original if no match found
        return user_type


# Catalog type aliases for user-friendly input
# Maps common user terms to database catalog_type values
CATALOG_TYPE_ALIASES = {
    # Thesis variants
    "thesis": "Karya Ilmiah - Thesis (S2) - Reference",
    "s2": "Karya Ilmiah - Thesis (S2) - Reference",
    "master": "Karya Ilmiah - Thesis (S2) - Reference",
    "magister": "Karya Ilmiah - Thesis (S2) - Reference",
    
    # Skripsi variants
    "skripsi": "Karya Ilmiah - Skripsi (S1) - Reference",
    "s1": "Karya Ilmiah - Skripsi (S1) - Reference",
    "bachelor": "Karya Ilmiah - Skripsi (S1) - Reference",
    "sarjana": "Karya Ilmiah - Skripsi (S1) - Reference",
    
    # Disertasi variants
    "disertasi": "Karya Ilmiah - Disertasi (S3) - Reference",
    "s3": "Karya Ilmiah - Disertasi (S3) - Reference",
    "doktor": "Karya Ilmiah - Disertasi (S3) - Reference",
    "phd": "Karya Ilmiah - Disertasi (S3) - Reference",
    "doctoral": "Karya Ilmiah - Disertasi (S3) - Reference",
    
    # Journal variants
    "jurnal internasional": "Jurnal Internasional - Reference",
    "international journal": "Jurnal Internasional - Reference",
    "jurnal nasional": "Jurnal Nasional - Reference",
    "national journal": "Jurnal Nasional - Reference",
    "jurnal terakreditasi": "Jurnal Terakreditasi DIKTI - Reference",
    "accredited journal": "Jurnal Terakreditasi DIKTI - Reference",
    
    # E-book variants
    "e-book": "Buku - Elektronik (E-Book)",
    "ebook": "Buku - Elektronik (E-Book)",
    "buku elektronik": "Buku - Elektronik (E-Book)",
    "electronic book": "Buku - Elektronik (E-Book)",
    "kindle": "Buku - Elektronik (E-Book) Kindle",
    
    # Proceeding variants
    "proceeding": "Proceeding (Electronic)",
    "konferensi": "Proceeding (Electronic)",
    "conference": "Proceeding (Electronic)",
    "seminar": "Proceeding (Electronic)",
    
    # Article variants
    "artikel": "Artikel - Restricted Use",
    "article": "Artikel - Restricted Use",
    "e-article": "E-Article",
    
    # Case studies
    "case study": "Case Studies",
    "case studies": "Case Studies",
    "studi kasus": "Case Studies",
    
    # Other
    "modul": "Modul Praktikum ( Electronic )",
    "module": "Modul Praktikum ( Electronic )",
    "eposter": "ePoster",
    "poster": "ePoster",
}


def get_catalog_type_suggestions(query: str) -> list[str]:
    """
    Get catalog type suggestions based on user input.
    
    Args:
        query: Partial user input
        
    Returns:
        List of matching catalog type suggestions
    """
    query_lower = query.lower()
    matches = []
    
    for alias, db_value in CATALOG_TYPE_ALIASES.items():
        if query_lower in alias or alias in query_lower:
            if db_value not in matches:
                matches.append(db_value)
    
    return matches[:5]  # Return top 5 matches


def normalize_catalog_type(user_input: str) -> Optional[str]:
    """
    Normalize user input to database catalog type.
    
    Args:
        user_input: User's catalog type input
        
    Returns:
        Normalized catalog type or None if no match
    """
    user_lower = user_input.lower().strip()
    
    # Direct match
    if user_lower in CATALOG_TYPE_ALIASES:
        return CATALOG_TYPE_ALIASES[user_lower]
    
    # Partial match
    for alias, db_value in CATALOG_TYPE_ALIASES.items():
        if alias in user_lower or user_lower in alias:
            return db_value
    
    return None
