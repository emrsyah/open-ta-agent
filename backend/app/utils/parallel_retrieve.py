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
    top_k: int = 3,
    use_vector: bool = True
) -> tuple[str, List[Any]]:
    """
    Execute multiple retrievals in parallel and merge results.

    Args:
        retriever: PaperRetriever instance
        queries: List of search queries (2-4 recommended)
        top_k: Papers to retrieve per query
        use_vector: Whether to use vector search

    Returns:
        Tuple of (combined_context_string, all_papers_deduplicated)
    """
    if not queries:
        return "No queries provided.", []

    logger.info(f"[PARALLEL] Executing {len(queries)} retrievals in parallel")

    # Create retrieval tasks
    tasks = [
        retriever.get_papers_with_context(query, top_k=top_k)
        for query in queries
    ]

    # Execute in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    all_contexts = []
    all_papers = []
    seen_ids = set()

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"[PARALLEL] Query {i} failed: {result}")
            continue

        context, papers = result

        # Add context with query label
        if context and context != "No relevant papers found in the catalog.":
            all_contexts.append(f"## Query: {queries[i]}\n{context}")

        # Deduplicate papers by ID
        for paper in papers:
            if paper.id not in seen_ids:
                seen_ids.add(paper.id)
                all_papers.append(paper)

    # Combine contexts
    combined_context = "\n\n".join(all_contexts) if all_contexts else "No relevant papers found."

    logger.info(
        f"[PARALLEL] Retrieved {len(all_papers)} unique papers "
        f"from {len(queries)} queries"
    )

    return combined_context, all_papers
