"""
Parallel retrieval orchestrator for multi-query search.
"""

import asyncio
import logging
from typing import Any, List

logger = logging.getLogger(__name__)


async def parallel_retrieve(
    retriever: Any,
    queries: List[str],
    top_k: int = 5,
    use_vector: bool = True,
    paper_offset: int = 0,
) -> tuple[str, List[Any]]:
    """
    Execute multiple retrievals in parallel and merge results.

    Args:
        retriever: PaperRetriever instance
        queries: List of search queries (2-4 recommended)
        top_k: Papers to retrieve per query
        use_vector: Whether to use vector search
        paper_offset: Number of papers already retrieved in prior steps.
                      Used to produce globally unique Paper N labels so that
                      the final context fed to the LLM has no duplicate numbers.

    Returns:
        Tuple of (combined_context_string, all_papers_deduplicated)
    """
    if not queries:
        return "No queries provided.", []

    logger.info(f"[PARALLEL] Executing {len(queries)} retrievals in parallel")

    # Fetch raw papers per sub-query (no numbering yet — we deduplicate first)
    tasks = [
        retriever.search(query, limit=top_k)
        for query in queries
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Deduplicate across sub-queries
    all_papers: List[Any] = []
    seen_ids: set = set()
    query_paper_map: List[tuple[str, List[Any]]] = []  # (query, papers_for_that_query)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"[PARALLEL] Query {i} failed: {result}")
            query_paper_map.append((queries[i], []))
            continue

        papers: List[Any] = result
        unique_for_query: List[Any] = []
        for paper in papers:
            if paper.id not in seen_ids:
                seen_ids.add(paper.id)
                all_papers.append(paper)
                unique_for_query.append(paper)
        query_paper_map.append((queries[i], unique_for_query))

    # Build context with globally unique Paper N numbers (continuing from paper_offset)
    all_contexts = []
    global_idx = paper_offset + 1

    for query_text, papers in query_paper_map:
        if not papers:
            continue
        section_parts = []
        for paper in papers:
            section_parts.append(
                f"Paper {global_idx} (ID: {paper.id})\n"
                f"Title: {paper.title}\n"
                f"Authors: {', '.join(paper.authors)}\n"
                f"Year: {paper.year}\n"
                f"Abstract: {paper.abstract}\n"
            )
            global_idx += 1
        all_contexts.append(
            f"## Query: {query_text}\n" + "\n---\n".join(section_parts)
        )

    combined_context = "\n\n".join(all_contexts) if all_contexts else "No relevant papers found."

    logger.info(
        f"[PARALLEL] Retrieved {len(all_papers)} unique papers "
        f"from {len(queries)} queries (global Paper {paper_offset + 1}..{global_idx - 1})"
    )

    return combined_context, all_papers
