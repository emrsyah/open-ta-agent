"""
Query decomposition module for multi-angle research.
"""

import logging
from typing import List

import dspy

logger = logging.getLogger(__name__)


class QueryDecompositionSignature(dspy.Signature):
    """
    Decompose a complex research query into 2-4 focused sub-queries.

    Use decomposition_hint from the plan step if provided.
    Examples:
    - hint='methods:Random Forest,SVM,Neural Networks' → create 3 sub-queries
    - hint='aspects:accuracy,cost,privacy' → create 3 sub-queries
    - hint='papers:P123,P456' → extract info from specific papers
    - No hint → analyze query and decompose naturally

    Rules:
    - Create 2-4 sub-queries maximum
    - Each sub-query should be searchable independently
    - Sub-queries should be different angles, not redundant
    - Keep sub-queries focused and specific
    - Preserve the original question's intent across all sub-queries
    """

    question: str = dspy.InputField(desc="The original user question")
    decomposition_hint: str = dspy.InputField(
        desc="Optional hint in format 'type:item1,item2,item3' or None",
        default=None
    )
    sub_queries: List[str] = dspy.OutputField(
        desc="List of 2-4 focused sub-queries for parallel retrieval"
    )


class QueryDecomposer(dspy.Module):
    """
    Decompose complex queries into multiple sub-queries.

    Used when a plan step has query_strategy='multi_query'.
    Enables parallel retrieval of different angles/aspects.
    """

    def __init__(self):
        super().__init__()
        self.decompose = dspy.Predict(QueryDecompositionSignature)

    def forward(self, question: str, decomposition_hint: str | None = None) -> dspy.Prediction:
        """
        Decompose a question into sub-queries.

        Args:
            question: The original user question
            decomposition_hint: Optional hint from plan step (e.g., 'methods:A,B,C')

        Returns:
            Prediction with sub_queries list
        """
        if decomposition_hint:
            logger.info(f"[DECOMPOSER] Using hint: {decomposition_hint}")
        else:
            logger.info("[DECOMPOSER] No hint provided, analyzing query")

        result = self.decompose(
            question=question,
            decomposition_hint=decomposition_hint or ""
        )

        sub_queries = getattr(result, 'sub_queries', [])
        logger.info(f"[DECOMPOSER] Created {len(sub_queries)} sub-queries")

        return dspy.Prediction(sub_queries=sub_queries)
