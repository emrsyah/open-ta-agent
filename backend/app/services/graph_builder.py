"""
LangGraph graph builder for the RAG pipeline.

Wires all nodes together into a StateGraph and compiles it.
The compiled graph is used by RAGServiceLangGraph.

Design notes:
- classify_intent handles initial routing (general vs research)
- For research: acknowledge → create_plan → step_loop → generate_answer → gap detection
- Step loop uses a routing node to iterate through plan steps
- generate_query is called within classify_intent node to run in parallel via asyncio
"""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, START, END

from app.services.graph_state import RAGGraphState
from app.services.graph_nodes import (
    classify_intent,
    acknowledge,
    create_plan,
    execute_step,
    generate_answer_general,
    generate_answer,
    detect_gap,
    refine_answer,
    post_answer,
)

logger = logging.getLogger(__name__)


def build_rag_graph():
    """Build and compile the RAG LangGraph pipeline.

    Graph flow:
        START ──> classify_intent
                    ├── (general) ──> generate_answer_general ──> post_answer ──> END
                    └── (research) ──> acknowledge ──> create_plan ──> route_steps_node
                                                                        ├── execute_step ──> route_steps_node
                                                                        └── generate_answer ──> detect_gap
                                                                                                  ├── refine_answer ──> post_answer ──> END
                                                                                                  └── post_answer ──> END
    """
    workflow = StateGraph(RAGGraphState)

    # ── Add nodes ──────────────────────────────────────────────────────
    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("acknowledge", acknowledge)
    workflow.add_node("create_plan", create_plan)
    workflow.add_node("route_steps_node", route_steps_node)
    workflow.add_node("execute_step", execute_step)
    workflow.add_node("generate_answer_general", generate_answer_general)
    workflow.add_node("generate_answer", generate_answer)
    workflow.add_node("detect_gap", detect_gap)
    workflow.add_node("refine_answer", refine_answer)
    workflow.add_node("post_answer", post_answer)

    # ── Add edges ──────────────────────────────────────────────────────

    # Entry point
    workflow.add_edge(START, "classify_intent")

    # classify_intent routes via Command:
    #   → "acknowledge" (research)
    #   → "generate_answer_general" (general)

    # Research flow
    workflow.add_edge("acknowledge", "create_plan")
    workflow.add_edge("create_plan", "route_steps_node")

    # Step routing: route_steps_node decides next action
    workflow.add_conditional_edges("route_steps_node", _route_steps_decision, {
        "execute_step": "execute_step",
        "generate_answer": "generate_answer",
    })

    # execute_step loops back via Command → route_steps_node
    workflow.add_edge("execute_step", "route_steps_node")

    # General answer path
    workflow.add_edge("generate_answer_general", "post_answer")

    # Research answer path
    workflow.add_edge("generate_answer", "detect_gap")
    # detect_gap routes via Command → refine_answer or post_answer
    workflow.add_edge("refine_answer", "post_answer")

    # Exit
    workflow.add_edge("post_answer", END)

    # Compile without checkpointer (streaming via FastAPI SSE)
    graph = workflow.compile()

    logger.info(
        "[GRAPH] RAG LangGraph compiled with %d nodes",
        len(graph.nodes),
    )

    return graph


def route_steps_node(state: RAGGraphState) -> dict:
    """Pass-through node for step routing decisions.
    
    The actual routing logic is in _route_steps_decision (conditional edge).
    This node exists only because LangGraph's conditional_edges need a
    source node.
    """
    return {}


def _route_steps_decision(state: RAGGraphState) -> str:
    """Decide whether to execute next step or proceed to answer."""
    plan_steps = state.get("plan_steps", [])
    current_idx = state.get("current_step_idx", 0)

    if current_idx < len(plan_steps):
        return "execute_step"
    else:
        return "generate_answer"
