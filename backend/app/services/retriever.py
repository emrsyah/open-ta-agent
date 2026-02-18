"""
Paper retriever service for searching and retrieving papers.
"""

import json
import os
from typing import List
from app.core.models import Paper, PaperResult
from app.config import get_settings


class PaperRetriever:
    """
    Simple keyword-based paper retriever.
    
    TODO: Replace with vector search implementation using:
    - dspy.retrievers.Embeddings for semantic search
    - Hybrid approach: BM25 on title + vector on abstract
    """
    
    def __init__(self, papers: List[Paper] | None = None):
        """
        Initialize retriever with paper data.
        
        Args:
            papers: List of papers, or None to load from file
        """
        if papers:
            self.papers = papers
        else:
            self.papers = self._load_papers()
    
    def _load_papers(self) -> List[Paper]:
        """Load papers from JSON file or use defaults."""
        settings = get_settings()
        data_path = settings.PAPERS_DATA_PATH
        
        if os.path.exists(data_path):
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [Paper(**p) for p in data]
        
        # Return default mock data
        return self._get_default_papers()
    
    def _get_default_papers(self) -> List[Paper]:
        """Default Telkom-themed papers for testing."""
        return [
            Paper(
                id="paper_001",
                title="Deep Learning Approaches for Natural Language Processing",
                authors=["Dr. Ahmad Rizky", "Dr. Siti Nurhaliza"],
                abstract="This paper explores various deep learning techniques including transformers and BERT for NLP tasks. We evaluate performance on Indonesian language datasets.",
                year=2023,
                keywords=["deep learning", "NLP", "transformers"]
            ),
            Paper(
                id="paper_002",
                title="Machine Learning Applications in Telecommunications",
                authors=["Prof. Budi Santoso", "Dr. Maya Sari"],
                abstract="A comprehensive study on applying machine learning algorithms to optimize network traffic and predict system failures in telecom infrastructure.",
                year=2024,
                keywords=["machine learning", "telecom", "optimization"]
            ),
            Paper(
                id="paper_003",
                title="Computer Vision for Smart Cities",
                authors=["Dr. Dedi Kurniawan"],
                abstract="Implementation of computer vision algorithms for traffic monitoring, pedestrian detection, and smart surveillance systems in urban environments.",
                year=2023,
                keywords=["computer vision", "smart city", "AI"]
            ),
            Paper(
                id="paper_004",
                title="Blockchain Technology in Supply Chain Management",
                authors=["Dr. Eko Prasetyo", "Dr. Fitriani", "Rizal Maulana"],
                abstract="This research investigates the application of blockchain technology to improve transparency and traceability in supply chain management systems.",
                year=2024,
                keywords=["blockchain", "supply chain"]
            ),
            Paper(
                id="paper_005",
                title="IoT Security: Challenges and Solutions",
                authors=["Dr. Gita Permata"],
                abstract="An analysis of security vulnerabilities in IoT devices and proposed cryptographic solutions to protect against common attack vectors.",
                year=2022,
                keywords=["IoT", "security", "cryptography"]
            ),
        ]
    
    def search(
        self,
        query: str,
        limit: int = 5,
        search_field: str = "all"
    ) -> List[PaperResult]:
        """
        Search papers by keyword.
        
        Args:
            query: Search query
            limit: Maximum results
            search_field: Which field to search ('all', 'title', 'abstract', 'authors')
            
        Returns:
            List of papers with relevance scores
        """
        query_lower = query.lower()
        query_words = query_lower.split()
        matches = []
        
        for paper in self.papers:
            score = 0
            
            # Check title (higher weight)
            if search_field in ("all", "title"):
                title_lower = paper.title.lower()
                if any(word in title_lower for word in query_words):
                    score += 3
                if query_lower in title_lower:
                    score += 5  # Exact match bonus
            
            # Check abstract
            if search_field in ("all", "abstract"):
                abstract_lower = paper.abstract.lower()
                if any(word in abstract_lower for word in query_words):
                    score += 1
                if query_lower in abstract_lower:
                    score += 2
            
            # Check authors
            if search_field in ("all", "authors"):
                authors_text = " ".join(paper.authors).lower()
                if any(word in authors_text for word in query_words):
                    score += 2
            
            if score > 0:
                paper_dict = paper.model_dump()
                paper_dict["relevance_score"] = score
                matches.append((score, PaperResult(**paper_dict)))
        
        # Sort by relevance and return top results
        matches.sort(key=lambda x: x[0], reverse=True)
        return [paper for _, paper in matches[:limit]]
    
    def get_context(self, query: str, top_k: int = 3) -> str:
        """
        Get formatted context string for RAG.
        
        Args:
            query: Search query
            top_k: Number of papers to include
            
        Returns:
            Formatted context string
        """
        papers = self.search(query, limit=top_k)
        
        if not papers:
            return "No relevant papers found."
        
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
    
    def get_all_papers(self) -> List[Paper]:
        """Return all papers."""
        return self.papers
    
    def get_paper_by_id(self, paper_id: str) -> Paper | None:
        """Get a single paper by ID."""
        for paper in self.papers:
            if paper.id == paper_id:
                return paper
        return None
