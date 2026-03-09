"""
Custom Research Agent — LangChain create_agent implementation.

Replaces Deep Agents with a lean, research-specific agent that has exactly
3 tools instead of ~13.  Context is ~1500 tokens vs ~6500, which allows
cheaper/faster models and eliminates the "tool call then stop" failure mode.

Tools:
  create_plan(steps)          — plan-first behaviour for complex queries
  search_papers(...)          — semantic vector search in Telkom catalog
  get_paper_details(ids)      — batch full-metadata fetch for follow-up/compare

SSE Event Contract (same as existing frontend use-streaming-chat.ts):
  agent_start       — session begins
  status            — high-level status ("planning", "searching", "reading", "synthesizing")
  plan              — create_plan result  {steps: list[str]}
  step_start        — a logical step begins
  step_done         — a logical step completed
  tool_call_start   — tool invocation begins  {tool, tool_call_id, step_id}
  tool_call_args    — streamed argument JSON chunk
  tool_call_done    — tool finished  {success, summary}
  search_result     — paper list from search_papers  {query, paper_count, papers[]}
  answer_start      — final answer tokens begin
  token             — single answer token
  citation_audit    — inline citation check  {cited_count, ...}
  done              — final payload  {content, sources, duration_ms}
  title             — generated conversation title
  error             — error message
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator, List, Optional

from langchain.agents import create_agent
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_openrouter import ChatOpenRouter
from langfuse import observe

from app.config import get_settings
from app.core.models import CitedPaper
from app.services.retriever import PaperRetriever
from app.utils.streaming import _audit_citations, format_sse

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================

def _truncate(s: str, max_len: int = 200) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


def _safe_json(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return None
    return raw


def _prepare_model_name(name: str) -> str:
    """Strip the 'openrouter/' prefix that DSPy uses but ChatOpenRouter doesn't want."""
    return name.removeprefix("openrouter/")


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """\
You are **OpenTA Agent**, an expert research assistant for the Telkom University \
academic paper catalog.

## Decision Tree — choose ONE path before acting

### Path A — Casual / Off-topic
Greetings, thanks, meta questions about yourself → respond with plain text, \
NO tools.

### Path B — Simple single-topic search
User wants papers on ONE topic with no comparison or synthesis needed.
→ Call `search_papers` immediately.  Do NOT call `create_plan` first.
Example: "cari paper tentang deep learning" → `search_papers(query="deep learning")`

### Path C — Complex query (multi-topic, comparison, literature review, synthesis)
User asks about MULTIPLE topics, wants papers compared, or requests a structured \
literature review.
→ Step 1: Call `create_plan` with a list of concise step labels.
→ Step 2–N: Execute each step using `search_papers` or `get_paper_details`.
→ Final: Write a comprehensive answer only AFTER all steps are done.

Examples of complex queries that require `create_plan`:
- "bandingkan CNN dan RNN untuk klasifikasi gambar"
- "buat literature review tentang NLP di Telkom"
- "apa perbedaan skripsi tentang IoT dari 2020 sampai 2024?"

### Path D — Follow-up about previously seen papers
User refers to papers already listed in the conversation (e.g. "paper ke-2", \
"jelaskan paper 1 dan 3 lebih detail").
→ Call `get_paper_details` with the IDs from earlier in the conversation.
→ Do NOT search again unless the user explicitly asks for new papers.

---

## Tool Usage Rules

### create_plan
- Steps should be short, action-oriented labels: "Search X", "Search Y", \
"Compare X and Y", "Synthesize findings".
- After calling `create_plan`, IMMEDIATELY call the first tool — do NOT pause.

### search_papers
- The `query` argument MUST be in English and MUST be semantically optimized — \
never pass the raw user message as-is.
- Translate and distill the user's intent into concise English keywords:
  - "bisakah carikan paper tentang penggunaan big data di sentimen analisis" \
→ `query="big data sentiment analysis"`
  - "cari skripsi tentang sistem rekomendasi berbasis collaborative filtering" \
→ `query="collaborative filtering recommendation system"`
  - "paper deep learning untuk deteksi objek" → `query="deep learning object detection"`
- Extract and apply filters from natural language BEFORE calling:
  - year: "dari 2020" → year_from=2020 | "sebelum 2023" → year_to=2023
  - type: "skripsi" → catalog_type="Karya Ilmiah - Skripsi (S1) - Reference"
  - type: "thesis/S2" → catalog_type="Karya Ilmiah - Thesis (S2) - Reference"
  - type: "disertasi/S3" → catalog_type="Karya Ilmiah - Disertasi (S3) - Reference"
  - type: "jurnal" → catalog_type="Jurnal Internasional - Reference"
  - type: "proceeding" → catalog_type="Proceeding (Electronic)"
- Call multiple times with different queries to gather comprehensive results.

### get_paper_details
- Pass ALL relevant paper IDs in a single call (batch).
- Use this when the user asks for deeper detail on specific papers, \
or when you need abstracts for a detailed comparison.

---

## Writing the Answer (ONLY after all tool calls are done)

- Write in the SAME LANGUAGE the user used (Indonesian → Indonesian answer).
- Use inline citations `[N]` where N is the paper number returned by the tools.
- Every factual claim about a paper MUST have a citation.
- Use headings and bullet points for multi-paper or comparative answers.
- If no papers are found, say so honestly and suggest alternative keywords.
- Do NOT repeat tool call results verbatim — synthesize and explain.
"""


# ============================================================================
# Tool Definitions
# ============================================================================

def _make_tools(retriever: PaperRetriever):
    """
    Return the 3 research tools bound to the given retriever instance.
    All tools are native async @tool functions — no sync bridge needed.
    """

    # ------------------------------------------------------------------
    # Tool 1: create_plan
    # ------------------------------------------------------------------

    @tool
    def create_plan(steps: List[str]) -> str:
        """Plan the research task before executing it.

        Call this tool FIRST for any complex query that requires multiple
        searches, comparisons, or a structured literature review.
        Do NOT call it for simple single-topic lookups or casual questions.

        Args:
            steps: Ordered list of concise step labels describing what you will
                   do next, e.g. ["Search CNN papers", "Search RNN papers",
                   "Compare and synthesize findings"].

        Returns:
            JSON confirmation with the planned steps so you can track progress.
        """
        return json.dumps({"status": "plan_created", "steps": steps}, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Tool 2: search_papers
    # ------------------------------------------------------------------

    @tool
    async def search_papers(
        query: str,
        limit: int = 5,
        catalog_type: str = "",
        year_from: int = 0,
        year_to: int = 0,
    ) -> str:
        """Search for research papers in the Telkom University academic catalog.

        Use this whenever the user asks about research papers, academic topics,
        theses, or scholarly work.  You may call it multiple times with
        different queries to gather comprehensive results.

        IMPORTANT: The `query` argument must ALWAYS be in English and must be a
        concise semantic summary of what the user is looking for — never pass
        the raw user message.  Examples:
          - user: "penggunaan big data di sentimen analisis"
            → query="big data sentiment analysis"
          - user: "deep learning untuk klasifikasi teks"
            → query="deep learning text classification"

        Args:
            query: Concise English keywords for semantic search.
            limit: Maximum papers to return (1–10, default 5).
            catalog_type: Optional filter (empty = all types).
                          E.g. "Karya Ilmiah - Skripsi (S1) - Reference".
            year_from: Minimum publication year, or 0 for no lower bound.
            year_to:   Maximum publication year, or 0 for no upper bound.

        Returns:
            JSON with status and list of papers including id, title, authors,
            year, abstract, keywords, and relevance_score.
        """
        limit = max(1, min(limit, 10))
        _catalog = catalog_type.strip() or None
        _year_from = year_from if year_from and year_from > 0 else None
        _year_to = year_to if year_to and year_to > 0 else None

        try:
            papers = await retriever.search(
                query=query,
                limit=limit,
                catalog_type=_catalog,
                year_from=_year_from,
                year_to=_year_to,
            )
        except Exception as exc:
            logger.error("[AGENT] search_papers error: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)})

        if not papers:
            return json.dumps({
                "status": "no_results",
                "message": "No papers found. Try broader keywords or remove filters.",
            })

        results = []
        for i, p in enumerate(papers, 1):
            abstract = p.abstract or ""
            results.append({
                "paper_number": i,
                "id": p.id,
                "title": p.title,
                "authors": p.authors,
                "year": p.year,
                "abstract": (abstract[:500] + "…") if len(abstract) > 500 else abstract,
                "keywords": p.keywords,
                "relevance_score": round(p.relevance_score, 4),
            })

        return json.dumps(
            {"status": "success", "count": len(results), "papers": results},
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # Tool 3: get_paper_details
    # ------------------------------------------------------------------

    @tool
    async def get_paper_details(paper_ids: List[int]) -> str:
        """Fetch full metadata for one or more papers by their integer IDs.

        Use this tool to retrieve complete details (full abstract, catalog type,
        publisher, access link, subject) when you need to do a thorough
        comparison or answer a detailed follow-up question about specific papers.
        Pass ALL relevant IDs in a single call.

        Args:
            paper_ids: List of integer paper IDs from previous search results.

        Returns:
            JSON list of paper records with all available metadata fields.
        """
        from app.database import get_session_factory
        from app.db.crud import CatalogCRUD

        factory = get_session_factory()
        if factory is None:
            return json.dumps({"status": "error", "message": "Database unavailable."})

        records = []
        try:
            async with factory() as session:
                crud = CatalogCRUD(session)
                for pid in paper_ids:
                    try:
                        catalog = await crud.get_by_id(int(pid))
                        if catalog:
                            records.append(catalog.to_dict())
                    except Exception as exc:
                        logger.warning("[AGENT] get_paper_details id=%s error: %s", pid, exc)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)})

        if not records:
            return json.dumps({"status": "not_found", "message": "No papers found for the given IDs."})

        return json.dumps(
            {"status": "success", "count": len(records), "papers": records},
            ensure_ascii=False,
        )

    return [create_plan, search_papers, get_paper_details]


# ============================================================================
# Source Extraction Helper
# ============================================================================

def _extract_sources(all_tool_messages: list) -> List[CitedPaper]:
    """
    Build a deduplicated CitedPaper list from collected ToolMessages.

    Goes through all search_papers results in call order, assigns
    sequential citation numbers, and deduplicates by paper ID.
    """
    seen: dict[str, CitedPaper] = {}
    counter = 1

    for msg in all_tool_messages:
        if not isinstance(msg, ToolMessage):
            continue
        if getattr(msg, "name", "") not in ("search_papers",):
            continue

        parsed = _safe_json(msg.content)
        if not isinstance(parsed, dict):
            continue

        for paper in parsed.get("papers", []):
            pid = str(paper.get("id", ""))
            if not pid or pid in seen:
                continue
            authors_raw = paper.get("authors", [])
            authors = authors_raw if isinstance(authors_raw, list) else [authors_raw]
            seen[pid] = CitedPaper(
                id=pid,
                title=paper.get("title", ""),
                authors=authors,
                abstract=paper.get("abstract", ""),
                year=int(paper.get("year") or 0),
                citation_number=counter,
            )
            counter += 1

    return list(seen.values())


# ============================================================================
# ResearchAgent
# ============================================================================

class ResearchAgent:
    """
    LangChain create_agent-powered research assistant.

    Compared to Deep Agents this has:
    - 3 domain-specific tools instead of ~13 generic ones
    - ~1500 token system prompt instead of ~6500
    - Plan-first behaviour via create_plan tool (agent decides when to use it)
    - Batch paper detail fetching via get_paper_details
    - Identical SSE event contract — zero frontend changes needed
    """

    def __init__(
        self,
        retriever: PaperRetriever | None = None,
        model_name: str | None = None,
    ):
        self.retriever = retriever or PaperRetriever()
        self.settings = get_settings()
        self.model_name = model_name or self.settings.AGENT_MODEL
        self._agent = None
        logger.info("[AGENT] Initialized with model: %s", self.model_name)

    # ------------------------------------------------------------------
    # Internal: lazy agent init
    # ------------------------------------------------------------------

    def _get_agent(self):
        if self._agent is None:
            model_name = _prepare_model_name(self.model_name)
            model = ChatOpenRouter(
                model=model_name,
                temperature=0,
                max_tokens=8192,
            )
            tools = _make_tools(self.retriever)
            self._agent = create_agent(
                model=model,
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
            )
            logger.info("[AGENT] create_agent initialized with %d tools", len(tools))
        return self._agent

    # ------------------------------------------------------------------
    # Internal: build LangChain messages from history + question
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        question: str,
        history: Optional[List[dict]] = None,
        language: str = "en-US",
        catalog_type: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        author: Optional[str] = None,
    ) -> list:
        """
        Convert flat history dicts + current question into LangChain message list.

        History entries are expected to have "role" (user/assistant) and "content".
        Active filters from the request are appended to the user message so the
        agent can apply them without re-parsing natural language.
        """
        messages = []

        # Inject conversation history
        if history:
            for turn in history:
                role = turn.get("role", "")
                content = turn.get("content") or turn.get("answer") or turn.get("question") or ""
                if not content:
                    # Legacy format from old session_manager: {question, answer}
                    if role in ("user", "human"):
                        content = turn.get("question", "")
                    else:
                        content = turn.get("answer", "")
                if role in ("user", "human") and content:
                    messages.append(HumanMessage(content=content))
                elif role in ("assistant", "ai") and content:
                    messages.append(AIMessage(content=content))

        # Build the current user message, appending filter hints if present
        user_text = question
        filter_parts = []
        if language and not language.startswith("en"):
            filter_parts.append(f"[respond in language: {language}]")
        if catalog_type:
            filter_parts.append(f"[filter catalog_type: {catalog_type}]")
        if year_from:
            filter_parts.append(f"[filter year_from: {year_from}]")
        if year_to:
            filter_parts.append(f"[filter year_to: {year_to}]")
        if author:
            filter_parts.append(f"[filter author: {author}]")
        if filter_parts:
            user_text = user_text + "\n\n" + " ".join(filter_parts)

        messages.append(HumanMessage(content=user_text))
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
        """Non-streaming invocation. Returns {answer, sources, search_query}."""
        agent = self._get_agent()
        messages = self._build_messages(
            question, history, language, catalog_type, year_from, year_to, author
        )

        try:
            result = await agent.ainvoke({"messages": messages})
            final_msg = result["messages"][-1]
            answer = final_msg.content if hasattr(final_msg, "content") else str(final_msg)

            sources = _extract_sources(result.get("messages", []))
            search_query = None
            for msg in result.get("messages", []):
                if isinstance(msg, ToolMessage) and getattr(msg, "name", "") == "search_papers":
                    parsed = _safe_json(msg.content)
                    if isinstance(parsed, dict) and parsed.get("papers"):
                        # find the args from the preceding AIMessage
                        break

            return {"answer": answer, "sources": sources, "search_query": search_query}

        except Exception as exc:
            logger.error("[AGENT] chat() error: %s", exc, exc_info=True)
            return {"answer": f"Error: {exc}", "sources": [], "search_query": None}

    # ------------------------------------------------------------------
    # Streaming chat — Manus-like SSE activity feed
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
    ) -> AsyncGenerator[str, None]:
        """
        Stream the agent response as rich SSE events.

        Uses stream_mode=["messages", "updates"] from LangChain's create_agent:
        - "messages" mode: delivers AIMessageChunk tokens and tool_call_chunks
        - "updates" mode: delivers completed node results (tool results)

        All emitted events match the SSE contract already consumed by
        use-streaming-chat.ts — no frontend changes required.
        """
        agent = self._get_agent()
        messages = self._build_messages(
            question, history, language, catalog_type, year_from, year_to, author
        )
        t_start = time.time()

        logger.info(
            "[AGENT] stream_response start | question=%r | catalog_type=%s"
            " | year_from=%s | year_to=%s",
            question, catalog_type, year_from, year_to,
        )

        # ── Emit session start ─────────────────────────────────────────
        yield format_sse({
            "type": "agent_start",
            "message": "Starting research agent…",
            "question": question,
            "timestamp": t_start,
        })

        # ── State accumulators ─────────────────────────────────────────
        final_answer = ""
        all_tool_messages: list = []
        search_query: str | None = None
        emitted_answer_start = False

        # Tool call tracking: call_id → {name, args_buffer}
        active_tool_calls: dict[str, dict] = {}
        arg_buffers: dict[str, str] = {}

        # Step counter for unique step IDs
        step_counter = 0
        active_step_id: str | None = None

        # Search queries already emitted (to avoid duplicates in step_action)
        search_queries_seen: set[str] = set()

        event_count = 0

        try:
            async for stream_mode, data in agent.astream(
                {"messages": messages},
                stream_mode=["messages", "updates"],
                config={"recursion_limit": 50},
            ):
                event_count += 1

                # ============================================================
                # "messages" mode — token chunks and tool call chunks
                # ============================================================
                if stream_mode == "messages":
                    # LangChain delivers (message_chunk, metadata) tuples
                    message = data[0] if isinstance(data, (tuple, list)) and data else data

                    # Skip ToolMessages here — handled in "updates" mode
                    if isinstance(message, ToolMessage):
                        continue

                    if not isinstance(message, (AIMessageChunk, AIMessage)):
                        continue

                    # Full AIMessage (not a chunk): collect for source extraction
                    if isinstance(message, AIMessage) and not isinstance(message, AIMessageChunk):
                        continue

                    # ── Tool call chunks (argument streaming) ──────────────
                    tc_chunks = getattr(message, "tool_call_chunks", None) or []
                    for tc_chunk in tc_chunks:
                        tool_name = tc_chunk.get("name") or ""
                        call_id = tc_chunk.get("id") or ""
                        args_piece = tc_chunk.get("args") or ""

                        # New tool call starting
                        if tool_name and call_id and call_id not in active_tool_calls:
                            active_tool_calls[call_id] = {"name": tool_name}
                            arg_buffers[call_id] = ""

                            step_counter += 1
                            active_step_id = f"step_{step_counter}"

                            logger.info(
                                "[AGENT] Tool call start | tool=%s | id=%s | step=%s",
                                tool_name, call_id, active_step_id,
                            )

                            # Status hint based on tool
                            if tool_name == "create_plan":
                                yield format_sse({
                                    "type": "status",
                                    "step": "planning",
                                    "message": "Planning research steps…",
                                })
                            elif tool_name == "search_papers":
                                yield format_sse({
                                    "type": "status",
                                    "step": "searching",
                                    "message": "Searching the academic catalog…",
                                })
                            elif tool_name == "get_paper_details":
                                yield format_sse({
                                    "type": "status",
                                    "step": "reading",
                                    "message": "Reading paper details…",
                                })

                            yield format_sse({
                                "type": "tool_call_start",
                                "source": "main",
                                "tool": tool_name,
                                "tool_call_id": call_id,
                                "step_id": active_step_id,
                                "is_subagent": False,
                            })

                            yield format_sse({
                                "type": "step_start",
                                "step_id": active_step_id,
                                "title": {
                                    "create_plan": "Planning",
                                    "search_papers": "Searching Papers",
                                    "get_paper_details": "Reading Paper Details",
                                }.get(tool_name, tool_name),
                                "description": "",
                            })

                        # Accumulate and stream argument chunks
                        if args_piece:
                            effective_id = call_id or (
                                list(active_tool_calls)[-1] if active_tool_calls else None
                            )
                            if effective_id:
                                arg_buffers[effective_id] = arg_buffers.get(effective_id, "") + args_piece

                                yield format_sse({
                                    "type": "tool_call_args",
                                    "source": "main",
                                    "tool_call_id": effective_id,
                                    "tool": active_tool_calls.get(effective_id, {}).get("name", ""),
                                    "args_chunk": args_piece,
                                })

                                # Emit step_action with search query as soon as it's parseable
                                current_tool = active_tool_calls.get(effective_id, {}).get("name", "")
                                if current_tool == "search_papers":
                                    parsed_args = _safe_json(arg_buffers[effective_id])
                                    if isinstance(parsed_args, dict):
                                        q = parsed_args.get("query", "")
                                        if q and q not in search_queries_seen:
                                            search_queries_seen.add(q)
                                            search_query = q
                                            yield format_sse({
                                                "type": "step_action",
                                                "step_id": active_step_id,
                                                "action": "search",
                                                "query": q,
                                                "args": parsed_args,
                                            })

                    # ── Regular text content tokens (the final answer) ─────
                    content = getattr(message, "content", "") or ""
                    if content and not tc_chunks:
                        if not emitted_answer_start:
                            emitted_answer_start = True
                            yield format_sse({"type": "status", "step": "synthesizing", "message": "Writing answer…"})
                            yield format_sse({"type": "answer_start"})
                        final_answer += content
                        yield format_sse({"type": "token", "content": content, "source": "main"})

                # ============================================================
                # "updates" mode — completed node results (tool outputs)
                # ============================================================
                elif stream_mode == "updates":
                    if not isinstance(data, dict):
                        continue

                    for node_name, node_data in data.items():
                        if node_name not in ("tools", "model"):
                            continue

                        # ── tools node: tool execution results ─────────────
                        if node_name == "tools":
                            msgs = (
                                node_data.get("messages", [])
                                if isinstance(node_data, dict)
                                else []
                            )
                            for msg in msgs:
                                if not isinstance(msg, ToolMessage):
                                    continue

                                tool_name = getattr(msg, "name", "") or ""
                                call_id = getattr(msg, "tool_call_id", None) or ""
                                content_raw = getattr(msg, "content", "") or ""
                                all_tool_messages.append(msg)

                                logger.info(
                                    "[AGENT] Tool result | tool=%s | id=%s",
                                    tool_name, call_id,
                                )

                                # ── create_plan result ──────────────────────
                                if tool_name == "create_plan":
                                    parsed = _safe_json(content_raw)
                                    steps: list[str] = []
                                    if isinstance(parsed, dict):
                                        steps = parsed.get("steps", [])
                                    if steps:
                                        yield format_sse({"type": "plan", "steps": steps})
                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": "main",
                                        "tool_call_id": call_id,
                                        "tool": tool_name,
                                        "success": True,
                                        "summary": f"Created {len(steps)} steps",
                                    })
                                    yield format_sse({
                                        "type": "step_done",
                                        "step_id": active_step_id or f"step_{step_counter}",
                                    })

                                # ── search_papers result ────────────────────
                                elif tool_name == "search_papers":
                                    parsed = _safe_json(content_raw)
                                    papers_list = []
                                    result_status = "unknown"
                                    if isinstance(parsed, dict):
                                        papers_list = parsed.get("papers", [])
                                        result_status = parsed.get("status", "unknown")

                                    # Recover query from arg buffer
                                    call_args = _safe_json(arg_buffers.get(call_id, "{}"))
                                    used_query = (
                                        call_args.get("query", "") if isinstance(call_args, dict) else ""
                                    )
                                    if used_query and not search_query:
                                        search_query = used_query

                                    yield format_sse({
                                        "type": "search_result",
                                        "source": "main",
                                        "tool_call_id": call_id,
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
                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": "main",
                                        "tool_call_id": call_id,
                                        "tool": tool_name,
                                        "success": result_status == "success",
                                        "summary": (
                                            f"Found {len(papers_list)} papers"
                                            if result_status == "success"
                                            else parsed.get("message", "No results")
                                            if isinstance(parsed, dict)
                                            else "No results"
                                        ),
                                    })
                                    yield format_sse({
                                        "type": "step_done",
                                        "step_id": active_step_id or f"step_{step_counter}",
                                    })

                                # ── get_paper_details result ─────────────────
                                elif tool_name == "get_paper_details":
                                    parsed = _safe_json(content_raw)
                                    count = 0
                                    if isinstance(parsed, dict):
                                        count = parsed.get("count", len(parsed.get("papers", [])))
                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": "main",
                                        "tool_call_id": call_id,
                                        "tool": tool_name,
                                        "success": True,
                                        "summary": f"Retrieved details for {count} paper(s)",
                                    })
                                    yield format_sse({
                                        "type": "step_done",
                                        "step_id": active_step_id or f"step_{step_counter}",
                                    })

                                # ── any other tool ──────────────────────────
                                else:
                                    yield format_sse({
                                        "type": "tool_call_done",
                                        "source": "main",
                                        "tool_call_id": call_id,
                                        "tool": tool_name,
                                        "success": True,
                                        "summary": _truncate(str(content_raw)),
                                    })

        except Exception as exc:
            logger.error("[AGENT] Stream error: %s", exc, exc_info=True)
            yield format_sse({"type": "error", "content": str(exc)})
            yield "data: [DONE]\n\n"
            return

        # ── Post-stream ────────────────────────────────────────────────
        logger.info(
            "[AGENT] Stream complete | events=%d | tool_calls=%d | answer_chars=%d",
            event_count, len(active_tool_calls), len(final_answer),
        )

        sources = _extract_sources(all_tool_messages)

        # Citation audit
        if sources:
            audit = _audit_citations(final_answer, sources)
            yield format_sse({"type": "citation_audit", **audit})

        duration_ms = int((time.time() - t_start) * 1000)
        yield format_sse({
            "type": "done",
            "content": final_answer,
            "sources": [s.model_dump() for s in sources],
            "duration_ms": duration_ms,
            "tool_calls_count": len(active_tool_calls),
        })

        # on_complete callback (save history / DB)
        if on_complete:
            try:
                await on_complete(
                    answer=final_answer,
                    sources=[s.model_dump() for s in sources],
                    search_query=search_query,
                )
            except Exception as exc:
                logger.warning("[AGENT] on_complete failed: %s", exc)

        # Title generation (first message only)
        if generate_title_fn and is_first_message and not is_incognito:
            try:
                title = await generate_title_fn(question, final_answer)
                yield format_sse({"type": "title", "content": title})
            except Exception as exc:
                logger.warning("[AGENT] Title generation failed: %s", exc)

        yield "data: [DONE]\n\n"

    # ------------------------------------------------------------------
    # Title generation
    # ------------------------------------------------------------------

    @observe(name="Agent Title Generation")
    async def generate_title(self, question: str, answer: str) -> str:
        """Generate a short conversation title (≤50 chars)."""
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
                f"Return ONLY the title, nothing else."
            )
            result = await title_model.ainvoke([HumanMessage(content=prompt)])
            title = (result.content if hasattr(result, "content") else str(result)).strip().strip('"').strip("'")
            return title[:47] + "…" if len(title) > 50 else title
        except Exception as exc:
            logger.warning("[AGENT] generate_title failed: %s", exc)
            q = question.strip()
            return q[:47] + "…" if len(q) > 50 else q


# ============================================================================
# Global singleton
# ============================================================================

_research_agent: ResearchAgent | None = None


def get_research_agent() -> ResearchAgent:
    """Return the global ResearchAgent instance (created on first call)."""
    global _research_agent
    if _research_agent is None:
        _research_agent = ResearchAgent()
    return _research_agent


def init_research_agent(
    retriever: PaperRetriever | None = None,
    model_name: str | None = None,
) -> ResearchAgent:
    """Initialize (or re-initialize) the global ResearchAgent."""
    global _research_agent
    _research_agent = ResearchAgent(retriever=retriever, model_name=model_name)
    return _research_agent
