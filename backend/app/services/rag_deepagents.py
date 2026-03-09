"""
DeepAgents-based RAG service — Full agentic loop rewrite.

Uses LangChain's Deep Agents SDK to power an autonomous paper research
assistant that can:
  - Plan complex research tasks (built-in write_todos)
  - Autonomously decide when to search vs answer from context
  - Iterate: search → evaluate → refine → search again if needed
  - Stream token-by-token via LangGraph's message streaming

Emits a rich, Manus-like SSE event stream so the frontend can render
a detailed, real-time activity feed showing every step, tool call,
argument, result, and subagent lifecycle.

SSE Event Contract (ordered by typical emission):
  agent_start       — session begins
  status            — high-level status changes (planning, searching, …)
  plan              — write_todos result: list of planned steps
  step_start        — a logical step begins
  tool_call_start   — a tool invocation begins (name, id, source)
  tool_call_args    — streamed argument JSON for the active tool call
  tool_call_done    — tool execution finished, includes result summary
  search_result     — detailed search result (query, paper_count, papers[])
  subagent_spawn    — a subagent is being created (id, type, description)
  subagent_event    — forwarded event from inside a subagent
  subagent_done     — subagent finished, includes result preview
  step_done         — a logical step completed
  answer_start      — final answer tokens are about to stream
  token             — a single answer token (content)
  subagent_token    — a token from a subagent's internal stream
  citation_audit    — post-stream citation hallucination check
  done              — final answer + sources payload
  title             — generated conversation title
  error             — error message
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, List, Optional

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openrouter import ChatOpenRouter
from langfuse import observe

from app.config import get_settings
from app.core.models import CitedPaper
from app.services.retriever import PaperRetriever
from app.utils.streaming import _audit_citations, format_sse

logger = logging.getLogger(__name__)


# ============================================================================
# Custom Tool: Search Papers (async — runs on the main event loop)
# ============================================================================


def _create_search_papers_tool(retriever: PaperRetriever):
    """Create the search_papers tool as an async function.

    Deep Agents auto-converts plain functions into LangChain tools
    using the function signature + docstring for the schema.
    Async tools are awaited on the main event loop, so DB connections work.
    """

    async def search_papers(
        query: str,
        limit: int = 5,
        catalog_type: str = "",
        year_from: int = 0,
        year_to: int = 0,
    ) -> str:
        """Search for research papers in the Telkom University academic catalog.

        Use this tool whenever the user asks about research papers, academic
        topics, theses, or scholarly work. You can call this tool multiple
        times with different queries to gather comprehensive results.

        Args:
            query: Search keywords or question about papers. Be specific
                   and use academic terminology for best results.
            limit: Maximum number of papers to return (default 5, max 10).
            catalog_type: Optional filter by type: 'Skripsi', 'Thesis',
                          'Disertasi', 'Jurnal'. Leave empty for all types.
            year_from: Optional minimum publication year (e.g. 2020).
                       Use 0 to skip this filter.
            year_to: Optional maximum publication year (e.g. 2024).
                     Use 0 to skip this filter.

        Returns:
            JSON with status and list of papers including title, authors,
            year, abstract, keywords, and relevance score.
        """
        # Clamp limit
        limit = max(1, min(limit, 10))

        # Normalise optional filters
        _catalog_type = catalog_type if catalog_type else None
        _year_from = year_from if year_from and year_from > 0 else None
        _year_to = year_to if year_to and year_to > 0 else None

        try:
            papers = await retriever.search(
                query=query,
                limit=limit,
                catalog_type=_catalog_type,
                year_from=_year_from,
                year_to=_year_to,
            )
        except Exception as e:
            logger.error("[SEARCH] Search failed: %s", e)
            return json.dumps(
                {"status": "error", "message": f"Search failed: {e}"}
            )

        if not papers:
            return json.dumps(
                {
                    "status": "no_results",
                    "message": (
                        "No papers found for this query. "
                        "Try broadening your search or using different keywords."
                    ),
                }
            )

        results = []
        for i, paper in enumerate(papers, 1):
            abstract = paper.abstract or ""
            results.append(
                {
                    "paper_number": i,
                    "id": paper.id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "abstract": (abstract[:500] + "…") if len(abstract) > 500 else abstract,
                    "keywords": paper.keywords,
                    "relevance_score": paper.relevance_score,
                }
            )

        return json.dumps(
            {"status": "success", "count": len(results), "papers": results},
            ensure_ascii=False,
        )

    return search_papers


# ============================================================================
# Paper Researcher Subagent
# ============================================================================

def _create_paper_researcher_subagent(retriever: PaperRetriever) -> dict:
    """Create a specialized subagent for deep paper research.

    The main agent delegates isolated search tasks here so that large
    search result payloads don't clutter the main agent context.
    Subagent returns a structured summary report.
    """
    search_tool = _create_search_papers_tool(retriever)

    return {
        "name": "paper-researcher",
        "description": (
            "Specialized research agent for searching the Telkom University paper catalog. "
            "Delegate ONE research topic per call. Provide a clear task description like: "
            "'Search for papers about X and return a structured summary of findings.'"
        ),
        "system_prompt": (
            "You are a specialized academic paper researcher for the Telkom University catalog.\n"
            "Your job is to:\n"
            "1. Search for papers using the search_papers tool (call it 1-3 times with different keywords)\n"
            "2. Evaluate the results\n"
            "3. Return a structured report with: topic, paper count, key findings, and paper list\n\n"
            "Format your final report as:\n"
            "## Research Report: [Topic]\n"
            "**Papers found:** N\n"
            "**Key findings:**\n"
            "- [Finding 1]\n"
            "- [Finding 2]\n"
            "**Papers:**\n"
            "[N] Title (Year) — brief relevance note\n\n"
            "Be thorough but concise. Always search in English even if the topic is in Indonesian."
        ),
        "tools": [search_tool],
    }


# ============================================================================
# System prompt
# ============================================================================

SYSTEM_PROMPT = """\
You are **OpenTA Agent**, an expert research assistant for the Telkom University \
academic paper catalog.

## CRITICAL: Execution Loop

You operate in a tool-calling loop. After EVERY tool call, you will see the result \
and MUST decide what to do next. **NEVER output a text response until you have \
completed ALL research steps.** The loop is:

1. Call a tool (search_papers, write_todos, task, etc.)
2. Receive the result
3. Decide: need more tool calls? → call the next tool. All done? → write final answer.

**IMPORTANT:** After calling `write_todos`, you MUST immediately call `search_papers` \
or `task` to begin executing the plan. Do NOT write any text response after \
`write_todos` — go straight to the next tool call.

## When to Use Which Approach

### Casual Conversation (NO tools needed)
- Greetings, thanks, off-topic → respond directly with text
- Example: "halo", "terima kasih", "siapa kamu?"

### Simple Research (call search_papers directly, NO plan needed)
- Single topic paper lookup → just call `search_papers` immediately
- Example: "cari paper tentang NLP" → call `search_papers(query="NLP")`
- Do NOT call `write_todos` for simple single-topic searches

### Complex/Comparative Research (plan + execute)
- Multiple topics, comparisons, or multi-step requests
- Example: "bandingkan paper CNN dan RNN"
- Step 1: Call `write_todos` with your plan
- Step 2: IMMEDIATELY call `search_papers` or `task` for the first item
- Step 3: After getting results, call `search_papers` or `task` for the next item
- Step 4: Continue until ALL items are done
- Step 5: ONLY THEN write your final comprehensive answer
- Use `task` tool to delegate each search to the paper-researcher subagent

### Follow-Up Questions (NO search, NO plan)
- User asks about papers already in the conversation
- "jelaskan paper ke-2", "apa perbedaan paper 1 dan 3?"
- Answer directly from context

## Research Execution Rules
- Call `search_papers` with specific academic keywords (translate to English if needed)
- **ALWAYS parse and apply metadata filters** from natural language queries before searching
- For complex queries with 3+ topics: delegate searches to `paper-researcher` subagent using `task` tool
- Each subagent handles ONE research topic and returns a structured report
- **Always cite papers** using inline `[N]` notation (sequential across all searches)
- Every factual claim from a paper MUST have an inline citation
- Match the user's language in the final answer (Indonesian → respond in Indonesian)

## Metadata Filter Parsing
Extract and apply these filters from user queries before calling search_papers:

### Year Filters (year_from, year_to):
- "from 2023" → year_from=2023
- "after 2020" → year_from=2020
- "since 2022" → year_from=2022
- "before 2024" → year_to=2024
- "until 2023" → year_to=2023
- "in 2023" → year_from=2023, year_to=2023
- "between 2020 and 2024" → year_from=2020, year_to=2024
- "2020-2024" → year_from=2020, year_to=2024

### Document Type Filters (catalog_type):
- "thesis" or "skripsi" → catalog_type="Karya Ilmiah - Skripsi (S1) - Reference"
- "master thesis" or "S2" → catalog_type="Karya Ilmiah - Thesis (S2) - Reference"
- "dissertation" or "PhD" or "S3" → catalog_type="Karya Ilmiah - Disertasi (S3) - Reference"
- "journal" or "jurnal" → catalog_type="Jurnal Internasional - Reference" or "Jurnal Nasional - Reference"
- "conference" or "proceeding" → catalog_type="Proceeding (Electronic)"

### Examples:
- "find papers about AI from 2023" → search_papers(query="artificial intelligence", year_from=2023)
- "machine learning thesis from 2020 to 2024" → search_papers(query="machine learning", catalog_type="Karya Ilmiah - Thesis (S2) - Reference", year_from=2020, year_to=2024)
- "skripsi tentang IoT sebelum 2022" → search_papers(query="internet of things", catalog_type="Karya Ilmiah - Skripsi (S1) - Reference", year_to=2022)

## Writing Your Answer (ONLY after all searches are complete)
- Use clear headings and bullet points
- Group papers by theme if there are many
- Include a brief summary of key findings at the end
- If no papers found, be honest and suggest alternative keywords
"""


# ============================================================================
# Helpers
# ============================================================================


def _prepare_model_name(model_name: str) -> str:
    """Strip litellm prefix and normalise for OpenRouter."""
    if model_name.startswith("openrouter/"):
        model_name = model_name.replace("openrouter/", "", 1)
    if "gemini" in model_name.lower() and "/" not in model_name:
        model_name = f"google/{model_name}"
    return model_name


def _extract_sources_from_messages(messages: list) -> tuple[list[CitedPaper], str | None]:
    """Walk the message list and extract CitedPaper objects from ToolMessages.

    Returns (sources, search_query).
    """
    sources: list[CitedPaper] = []
    search_query: str | None = None
    paper_counter = 0

    for msg in messages:
        # Find ToolMessages that are responses to search_papers calls
        if isinstance(msg, ToolMessage) and msg.name == "search_papers":
            try:
                data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if isinstance(data, dict) and data.get("status") == "success":
                    for p in data.get("papers", []):
                        paper_counter += 1
                        sources.append(
                            CitedPaper(
                                id=p.get("id", ""),
                                title=p.get("title", ""),
                                authors=p.get("authors", []),
                                year=p.get("year", 0),
                                abstract=p.get("abstract", ""),
                                citation_number=paper_counter,
                            )
                        )
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # Find the search query from AIMessage tool_calls
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "search_papers":
                    args = tc.get("args", {})
                    if isinstance(args, dict):
                        search_query = args.get("query", search_query)

    return sources, search_query


def _safe_json_parse(s: str) -> dict | list | None:
    """Try to parse JSON, return None on failure."""
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def _truncate(s: str, max_len: int = 200) -> str:
    """Truncate a string for preview purposes."""
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


# ============================================================================
# DeepAgents RAG Service
# ============================================================================


class RAGServiceDeepAgents:
    """RAG service powered by Deep Agents SDK.

    Creates a compiled LangGraph agent with:
    - Built-in planning (write_todos) and context management
    - Custom search_papers tool for vector DB retrieval
    - Autonomous agentic loop (search → evaluate → refine)
    - Token-level streaming via ``stream_mode="messages"``

    Emits a Manus-like real-time activity feed via SSE events.
    """

    def __init__(
        self,
        retriever: PaperRetriever | None = None,
        model_name: str | None = None,
    ):
        self.retriever = retriever or PaperRetriever()
        self.settings = get_settings()
        self.model_name = model_name or self.settings.DEEPAGENTS_MODEL

        # Primary search tool (also shared with subagent)
        self._search_tool = _create_search_papers_tool(self.retriever)

        # Paper researcher subagent definition
        self._paper_researcher_subagent = _create_paper_researcher_subagent(self.retriever)

        # Lazy agent
        self._agent = None

        logger.info("[DEEP-AGENTS] Initialized with model: %s", self.model_name)

    # ------------------------------------------------------------------
    # Agent factory
    # ------------------------------------------------------------------

    def _get_agent(self):
        """Lazy-init the Deep Agent (compiled LangGraph)."""
        if self._agent is not None:
            return self._agent

        try:
            from deepagents import create_deep_agent
        except ImportError:
            logger.error(
                "[DEEP-AGENTS] deepagents not installed. Run: pip install deepagents"
            )
            raise

        model_name = _prepare_model_name(self.model_name)
        model = ChatOpenRouter(
            model=model_name,
            temperature=0,
            max_tokens=8192,
        )

        self._agent = create_deep_agent(
            model=model,
            tools=[self._search_tool],
            system_prompt=SYSTEM_PROMPT,
            subagents=[self._paper_researcher_subagent],
        )

        logger.info("[DEEP-AGENTS] Agent created successfully (with paper-researcher subagent)")
        return self._agent

    # ------------------------------------------------------------------
    # Build the message list
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        question: str,
        history: list[dict] | None = None,
        language: str = "en-US",
        catalog_type: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        author: str | None = None,
    ) -> list:
        """Build the messages list for the agent invocation."""
        messages = []

        # Inject active filters as system context
        filter_parts = []
        if catalog_type:
            filter_parts.append(f"catalog_type='{catalog_type}'")
        if year_from:
            filter_parts.append(f"year_from={year_from}")
        if year_to:
            filter_parts.append(f"year_to={year_to}")
        if author:
            filter_parts.append(f"author='{author}'")

        if filter_parts:
            messages.append(
                SystemMessage(
                    content=(
                        "The user has set the following filters. "
                        "Apply them to every search_papers call: "
                        + ", ".join(filter_parts)
                    )
                )
            )

        # Conversation history → HumanMessage/AIMessage pairs
        # Include paper sources so the agent can answer follow-up questions
        if history:
            for msg in history[-5:]:
                q = msg.get("question", "")
                a = msg.get("answer", "")
                if q:
                    messages.append(HumanMessage(content=q))
                if a:
                    # Build context: answer + sources summary
                    answer_content = a[:1500] if len(a) > 1500 else a
                    sources_data = msg.get("sources", [])
                    if sources_data:
                        papers_summary = "\n\nPapers referenced in this answer:\n"
                        for i, src in enumerate(sources_data, 1):
                            if isinstance(src, dict):
                                title = src.get("title", "Unknown")
                                authors = src.get("authors", [])
                                year = src.get("year", "")
                                abstract = src.get("abstract", "")[:200]
                                papers_summary += (
                                    f"[{i}] {title} ({year}) by {', '.join(authors) if isinstance(authors, list) else authors}\n"
                                    f"    Abstract: {abstract}\n"
                                )
                        answer_content += papers_summary
                    messages.append(AIMessage(content=answer_content))

        # Current question
        messages.append(HumanMessage(content=question))
        return messages

    # ------------------------------------------------------------------
    # Non-streaming chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        language: str = "en-US",
        source_preference: str = "all",
        catalog_type: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        author: Optional[str] = None,
        has_electronic_access: Optional[bool] = None,
    ) -> dict:
        """Non-streaming chat — runs the full agentic loop."""
        agent = self._get_agent()
        messages = self._build_messages(
            question, history, language, catalog_type, year_from, year_to, author
        )

        try:
            result = await agent.ainvoke(
                {"messages": messages},
                config={"recursion_limit": 50},
            )
            all_msgs = result.get("messages", [])

            # Final answer = last AI message
            final_answer = ""
            for msg in reversed(all_msgs):
                if isinstance(msg, AIMessage) and msg.content:
                    final_answer = msg.content
                    break

            sources, search_query = _extract_sources_from_messages(all_msgs)

            return {
                "answer": final_answer,
                "sources": sources,
                "rationale": None,
                "search_query": search_query,
            }
        except Exception as e:
            logger.error("[DEEP-AGENTS] Error in chat: %s", e, exc_info=True)
            return {
                "answer": f"I encountered an error while processing your request: {e}",
                "sources": [],
                "rationale": None,
                "search_query": None,
            }

    # ------------------------------------------------------------------
    # Streaming chat — Manus-like activity feed
    # ------------------------------------------------------------------

    async def stream_response(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        language: str = "en-US",
        source_preference: str = "all",
        catalog_type: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        author: Optional[str] = None,
        has_electronic_access: Optional[bool] = None,
        conversation_id: Optional[str] = None,
        is_incognito: bool = False,
        user_id: Optional[str] = None,
        on_complete: Any = None,
        generate_title_fn: Any = None,
        is_first_message: bool = False,
    ) -> Any:
        """Stream the Deep Agent response as rich SSE events.

        Produces a Manus-like activity feed where every tool call, argument,
        result, subagent lifecycle event, and answer token is emitted as a
        discrete, typed SSE event so the frontend can render a detailed,
        real-time, collapsible activity log.

        Uses multiple stream modes (updates, messages, custom) with
        subgraphs=True to capture both main agent and subagent execution.
        """
        agent = self._get_agent()
        messages = self._build_messages(
            question, history, language, catalog_type, year_from, year_to, author
        )

        t_start = time.time()

        logger.info(
            "[DEEP-AGENTS] stream_response start | question='%s' | catalog_type=%s | year_from=%s | year_to=%s | author=%s",
            question, catalog_type, year_from, year_to, author,
        )

        # -- Emit session start ----------------------------------------
        yield format_sse({
            "type": "agent_start",
            "message": "Starting research agent...",
            "question": question,
            "timestamp": t_start,
        })

        # ── Accumulators ──────────────────────────────────────────────
        final_answer = ""
        all_collected_messages: list = []
        search_query: str | None = None

        # Tool call tracking
        active_tool_calls: dict[str, dict] = {}  # call_id → {name, args_buffer, source, started_at}
        tool_call_arg_buffers: dict[str, str] = {}  # call_id → accumulated JSON arg string

        # Step tracking
        step_counter = 0
        active_step_id: str | None = None

        # Subagent tracking
        active_subagents: dict[str, dict] = {}  # tool_call_id → {type, status, description, events[]}

        # Answer tracking
        emitted_answer_start = False
        search_queries_emitted: set = set()

        event_count = 0
        try:
            async for stream_event in agent.astream(
                {"messages": messages},
                stream_mode=["updates", "messages", "custom"],
                subgraphs=True,
                config={"recursion_limit": 50},
            ):
                event_count += 1

                # Deep Agents with subgraphs=True yields (namespace, mode, data)
                # but without subgraphs it yields (mode, data)
                if isinstance(stream_event, tuple) and len(stream_event) == 3:
                    namespace, mode, data = stream_event
                elif isinstance(stream_event, tuple) and len(stream_event) == 2:
                    namespace = ()
                    mode, data = stream_event
                else:
                    logger.warning(
                        "[DEEP-AGENTS] Unexpected stream event type=%s value=%s",
                        type(stream_event).__name__, _truncate(str(stream_event), 200),
                    )
                    continue

                # Log ALL events for debugging
                logger.info(
                    "[DEEP-AGENTS] Stream event #%d | namespace=%s | mode=%s | data_type=%s | data_preview=%s",
                    event_count, namespace, mode, type(data).__name__,
                    _truncate(str(data), 300),
                )

                # Determine source context
                is_subagent = any(
                    (isinstance(seg, str) and seg.startswith("tools:"))
                    for seg in namespace
                )

                subagent_tool_call_id: str | None = None
                if is_subagent:
                    for seg in namespace:
                        if isinstance(seg, str) and seg.startswith("tools:"):
                            subagent_tool_call_id = seg.split(":", 1)[1] if ":" in seg else None
                            break

                source = subagent_tool_call_id if is_subagent else "main"

                # ============================================================
                # Mode: "updates" — Node/step completion events
                # ============================================================
                if mode == "updates":
                    if isinstance(data, dict):
                        node_names = list(data.keys())
                        logger.info("[DEEP-AGENTS] Updates event nodes: %s", node_names)
                    for node_name, node_data in (data.items() if isinstance(data, dict) else []):
                        if node_name not in ("model", "agent", "tools", "model_request"):
                            logger.info("[DEEP-AGENTS] Skipping unhandled node: %s", node_name)
                            continue

                        # ── Tools node: tool execution results ──
                        if node_name == "tools":
                            msgs = node_data.get("messages", []) if isinstance(node_data, dict) else []
                            for msg in msgs:
                                if not (hasattr(msg, "type") and msg.type == "tool"):
                                    continue

                                tool_name = getattr(msg, "name", "")
                                tool_msg_id = getattr(msg, "tool_call_id", None)
                                content_raw = getattr(msg, "content", "")
                                all_collected_messages.append(msg)

                                logger.info(
                                    "[DEEP-AGENTS] Tool result | tool=%s | source=%s | id=%s",
                                    tool_name, source, tool_msg_id,
                                )

                                # ── search_papers result ──
                                if tool_name == "search_papers":
                                    parsed = _safe_json_parse(content_raw) if isinstance(content_raw, str) else None
                                    papers_list = parsed.get("papers", []) if isinstance(parsed, dict) else []
                                    result_status = parsed.get("status", "unknown") if isinstance(parsed, dict) else "unknown"

                                    # Recover the query from our arg buffer
                                    call_args = _safe_json_parse(tool_call_arg_buffers.get(tool_msg_id, "{}"))
                                    used_query = call_args.get("query", "") if isinstance(call_args, dict) else ""

                                    logger.info(
                                        "[DEEP-AGENTS] search_papers result | query='%s' | status=%s | papers=%d | catalog_type=%s | year_from=%s | year_to=%s",
                                        used_query,
                                        result_status,
                                        len(papers_list),
                                        call_args.get("catalog_type", "") if isinstance(call_args, dict) else "",
                                        call_args.get("year_from", "") if isinstance(call_args, dict) else "",
                                        call_args.get("year_to", "") if isinstance(call_args, dict) else "",
                                    )

                                    yield format_sse({
                                        "type": "search_result",
                                        "source": source,
                                        "tool_call_id": tool_msg_id,
                                        "query": used_query,
                                        "status": result_status,
                                        "paper_count": len(papers_list),
                                        "papers": [
                                            {
                                                "number": p.get("paper_number", i + 1),
                                                "title": p.get("title", ""),
                                                "authors": p.get("authors", []),
                                                "year": p.get("year", 0),
                                                "relevance": p.get("relevance_score", 0),
                                            }
                                            for i, p in enumerate(papers_list)
                                        ],
                                    })

                                    # Also emit tool_call_done
                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": source,
                                        "tool_call_id": tool_msg_id,
                                        "tool": tool_name,
                                        "success": result_status == "success",
                                        "summary": f"Found {len(papers_list)} papers" if result_status == "success" else (parsed.get("message", "No results") if isinstance(parsed, dict) else "Error"),
                                    })

                                # ── write_todos result ──
                                elif tool_name == "write_todos":
                                    parsed = _safe_json_parse(content_raw) if isinstance(content_raw, str) else content_raw
                                    todos = parsed if isinstance(parsed, list) else (parsed.get("todos", []) if isinstance(parsed, dict) else [])
                                    steps = []
                                    for todo in todos:
                                        if isinstance(todo, dict):
                                            steps.append(todo.get("title", todo.get("task", str(todo))))
                                        else:
                                            steps.append(str(todo))
                                    if steps:
                                        yield format_sse({"type": "plan", "steps": steps})

                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": source,
                                        "tool_call_id": tool_msg_id,
                                        "tool": tool_name,
                                        "success": True,
                                        "summary": f"Created {len(steps)} tasks",
                                    })

                                # ── task (subagent delegation) result ──
                                elif tool_name == "task":
                                    result_preview = _truncate(str(content_raw))
                                    if tool_msg_id and tool_msg_id in active_subagents:
                                        active_subagents[tool_msg_id]["status"] = "complete"
                                        yield format_sse({
                                            "type": "subagent_done",
                                            "subagent_id": tool_msg_id,
                                            "subagent_type": active_subagents[tool_msg_id].get("type", "unknown"),
                                            "description": active_subagents[tool_msg_id].get("description", ""),
                                            "result_preview": result_preview,
                                        })

                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": source,
                                        "tool_call_id": tool_msg_id,
                                        "tool": tool_name,
                                        "success": True,
                                        "summary": result_preview,
                                    })

                                    yield format_sse({
                                        "type": "step_done",
                                        "step_id": active_step_id or f"subagent_{step_counter}",
                                    })

                                # ── Any other tool ──
                                else:
                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": source,
                                        "tool_call_id": tool_msg_id,
                                        "tool": tool_name,
                                        "success": True,
                                        "summary": _truncate(str(content_raw)),
                                    })

                                # Forward subagent-internal tool results
                                if is_subagent and subagent_tool_call_id:
                                    yield format_sse({
                                        "type": "subagent_event",
                                        "subagent_id": subagent_tool_call_id,
                                        "event": "tool_result",
                                        "tool": tool_name,
                                        "tool_call_id": tool_msg_id,
                                        "source": source,
                                    })

                # ============================================================
                # Mode: "messages" — Token streaming and tool call chunks
                # ============================================================
                elif mode == "messages":
                    if isinstance(data, (tuple, list)) and len(data) >= 1:
                        message = data[0]
                    else:
                        message = data

                    # ── ToolMessage (also captured in updates, skip here) ──
                    if isinstance(message, ToolMessage):
                        all_collected_messages.append(message)
                        continue

                    # ── AIMessageChunk: streaming tokens and tool call chunks ──
                    if isinstance(message, (AIMessageChunk, AIMessage)):
                        # Full AIMessage (not chunk) — collect for source extraction
                        if isinstance(message, AIMessage) and not isinstance(message, AIMessageChunk):
                            all_collected_messages.append(message)
                            continue

                        # ── Tool call chunks ──
                        if hasattr(message, "tool_call_chunks") and message.tool_call_chunks:
                            for tc_chunk in message.tool_call_chunks:
                                tool_name = tc_chunk.get("name")
                                call_id = tc_chunk.get("id")

                                # New tool call starting
                                if tool_name and call_id and call_id not in active_tool_calls:
                                    active_tool_calls[call_id] = {
                                        "name": tool_name,
                                        "source": source,
                                        "started_at": time.time(),
                                    }
                                    tool_call_arg_buffers[call_id] = ""

                                    step_counter += 1
                                    active_step_id = f"da_step_{step_counter}"

                                    logger.info(
                                        "[DEEP-AGENTS] Tool call start | tool=%s | call_id=%s | source=%s | step=%s",
                                        tool_name, call_id, source, active_step_id,
                                    )

                                    # Emit tool_call_start — the core Manus-like event
                                    yield format_sse({
                                        "type": "tool_call_start",
                                        "source": source,
                                        "tool": tool_name,
                                        "tool_call_id": call_id,
                                        "step_id": active_step_id,
                                        "is_subagent": is_subagent,
                                    })

                                    # Contextual step events
                                    if tool_name == "write_todos":
                                        yield format_sse({
                                            "type": "status",
                                            "step": "planning",
                                            "message": "Planning research steps...",
                                        })
                                    elif tool_name == "task":
                                        yield format_sse({
                                            "type": "step_start",
                                            "step_id": active_step_id,
                                            "title": "Delegating to Paper Researcher",
                                            "description": "Spawning subagent for focused research...",
                                        })
                                    elif tool_name == "search_papers":
                                        yield format_sse({
                                            "type": "step_start",
                                            "step_id": active_step_id,
                                            "title": "Searching Papers",
                                            "description": "Querying the academic catalog...",
                                            "source": source,
                                        })

                                    # Track subagent internal tool calls
                                    if is_subagent and subagent_tool_call_id:
                                        if subagent_tool_call_id in active_subagents:
                                            active_subagents[subagent_tool_call_id].setdefault("tool_calls", []).append({
                                                "tool": tool_name,
                                                "tool_call_id": call_id,
                                            })
                                        yield format_sse({
                                            "type": "subagent_event",
                                            "subagent_id": subagent_tool_call_id,
                                            "event": "tool_call",
                                            "tool": tool_name,
                                            "tool_call_id": call_id,
                                        })

                                # Accumulate argument chunks
                                args_chunk = tc_chunk.get("args", "")
                                if args_chunk:
                                    effective_id = call_id or (list(active_tool_calls.keys())[-1] if active_tool_calls else None)
                                    if effective_id:
                                        tool_call_arg_buffers[effective_id] = tool_call_arg_buffers.get(effective_id, "") + args_chunk

                                        # Emit the raw arg chunk so frontend can show args building up
                                        yield format_sse({
                                            "type": "tool_call_args",
                                            "source": source,
                                            "tool_call_id": effective_id,
                                            "tool": active_tool_calls.get(effective_id, {}).get("name", ""),
                                            "args_chunk": args_chunk,
                                        })

                                        # Try to parse complete args for rich events
                                        current_tool = active_tool_calls.get(effective_id, {}).get("name", "")
                                        full_args = tool_call_arg_buffers[effective_id]

                                        if current_tool == "search_papers":
                                            parsed_args = _safe_json_parse(full_args)
                                            if isinstance(parsed_args, dict):
                                                q = parsed_args.get("query", "")
                                                if q and q not in search_queries_emitted:
                                                    search_queries_emitted.add(q)
                                                    search_query = q
                                                    yield format_sse({
                                                        "type": "step_action",
                                                        "step_id": active_step_id,
                                                        "action": "search",
                                                        "query": q,
                                                        "args": parsed_args,
                                                    })

                                        elif current_tool == "task":
                                            parsed_args = _safe_json_parse(full_args)
                                            if isinstance(parsed_args, dict):
                                                task_desc = parsed_args.get("task", parsed_args.get("description", ""))
                                                subagent_type = parsed_args.get("subagent_type", parsed_args.get("category", "paper-researcher"))
                                                if task_desc and effective_id not in active_subagents:
                                                    active_subagents[effective_id] = {
                                                        "type": subagent_type,
                                                        "description": _truncate(task_desc, 150),
                                                        "status": "running",
                                                        "tool_calls": [],
                                                        "events": [],
                                                    }
                                                    yield format_sse({
                                                        "type": "subagent_spawn",
                                                        "subagent_id": effective_id,
                                                        "subagent_type": subagent_type,
                                                        "description": _truncate(task_desc, 150),
                                                        "step_id": active_step_id,
                                                        "args": parsed_args,
                                                    })

                                    continue

                        # ── Regular text content tokens ──
                        content = getattr(message, "content", "") or ""
                        if content:
                            if is_subagent:
                                yield format_sse({
                                    "type": "subagent_token",
                                    "subagent_id": subagent_tool_call_id,
                                    "content": content,
                                    "source": source,
                                })
                            else:
                                if not emitted_answer_start:
                                    emitted_answer_start = True
                                    logger.info("[DEEP-AGENTS] Answer streaming started")
                                    yield format_sse({"type": "answer_start"})
                                final_answer += content
                                yield format_sse({
                                    "type": "token",
                                    "content": content,
                                    "source": "main",
                                })

                # ============================================================
                # Mode: "custom" — Custom events from tools/agent
                # ============================================================
                elif mode == "custom":
                    yield format_sse({
                        "type": "custom_event",
                        "source": source,
                        "namespace": list(namespace),
                        "data": data,
                    })

        except Exception as e:
            logger.error("[DEEP-AGENTS] Stream error: %s", e, exc_info=True)
            yield format_sse({"type": "error", "content": str(e)})
            yield "data: [DONE]\n\n"
            return

        # -- Post-stream: extract sources from collected messages -------
        logger.info(
            "[DEEP-AGENTS] Stream complete | total_events=%d | tool_calls=%d | subagents=%d | answer_chars=%d | answer_started=%s",
            event_count, len(active_tool_calls), len(active_subagents), len(final_answer), emitted_answer_start,
        )
        if active_tool_calls:
            for cid, info in active_tool_calls.items():
                logger.info(
                    "[DEEP-AGENTS]   └─ tool=%s | source=%s | args=%s",
                    info.get("name"), info.get("source"),
                    _truncate(tool_call_arg_buffers.get(cid, ""), 120),
                )
        else:
            logger.warning("[DEEP-AGENTS] No tool calls were made — agent may have answered without searching!")
        sources, _ = _extract_sources_from_messages(all_collected_messages)

        # Extract search_query from accumulated tool call args
        if not search_query:
            for call_id, info in active_tool_calls.items():
                if info.get("name") == "search_papers":
                    parsed = _safe_json_parse(tool_call_arg_buffers.get(call_id, ""))
                    if isinstance(parsed, dict) and parsed.get("query"):
                        search_query = parsed["query"]
                        break

        # Citation audit
        if sources:
            audit = _audit_citations(final_answer, sources)
            yield format_sse({"type": "citation_audit", **audit})

        # Done event — frontend expects sources inside the done payload
        duration_ms = int((time.time() - t_start) * 1000)
        yield format_sse({
            "type": "done",
            "content": final_answer,
            "sources": [s.model_dump() for s in sources],
            "duration_ms": duration_ms,
            "tool_calls_count": len(active_tool_calls),
            "subagents_count": len(active_subagents),
        })

        # -- Callbacks -------------------------------------------------
        if on_complete:
            try:
                serialized_sources = [
                    s.model_dump() if hasattr(s, "model_dump") else s
                    for s in sources
                ]
                await on_complete(
                    answer=final_answer,
                    sources=serialized_sources,
                    search_query=search_query,
                )
            except Exception as e:
                logger.warning("[DEEP-AGENTS] on_complete failed: %s", e)

        if generate_title_fn and is_first_message and not is_incognito:
            try:
                title = await generate_title_fn(question, final_answer)
                yield format_sse({"type": "title", "content": title})
            except Exception as e:
                logger.warning("[DEEP-AGENTS] Title generation failed: %s", e)

        yield "data: [DONE]\n\n"

    # ------------------------------------------------------------------
    # Title generation
    # ------------------------------------------------------------------

    @observe(name="Title Generation")
    async def generate_title(self, question: str, answer: str) -> str:
        """Generate a short conversation title."""
        try:
            model_name = _prepare_model_name(self.model_name)
            title_model = ChatOpenRouter(
                model=model_name,
                temperature=0.3,
                max_tokens=100,
            )
            prompt = (
                f"Generate a short title (max 50 characters) for this conversation.\n\n"
                f"Question: {question}\n"
                f"Answer summary: {answer[:200]}\n\n"
                f"Return only the title, nothing else."
            )
            result = await title_model.ainvoke([HumanMessage(content=prompt)])
            title = result.content if hasattr(result, "content") else str(result)
            title = title.strip().strip('"').strip("'")
            if len(title) > 50:
                title = title[:47] + "..."
            return title
        except Exception as e:
            logger.warning("[DEEP-AGENTS] Title generation failed: %s", e)
            q = question.strip()
            return q[:50].rsplit(" ", 1)[0] + "…" if len(q) > 50 else q


# ============================================================================
# Global Instance
# ============================================================================

_rag_service_da: RAGServiceDeepAgents | None = None


def get_rag_service_da() -> RAGServiceDeepAgents:
    """Get or create the global DeepAgents RAG service instance."""
    global _rag_service_da
    if _rag_service_da is None:
        _rag_service_da = RAGServiceDeepAgents()
    return _rag_service_da


def init_rag_service_da(
    retriever: PaperRetriever | None = None,
    model_name: str | None = None,
) -> RAGServiceDeepAgents:
    """Initialize the global DeepAgents RAG service."""
    global _rag_service_da
    _rag_service_da = RAGServiceDeepAgents(retriever=retriever, model_name=model_name)
    return _rag_service_da
