"""
DeepAgents-based RAG service — Full agentic loop rewrite.

Uses LangChain's Deep Agents SDK to power an autonomous paper research
assistant that can:
  - Plan complex research tasks (built-in write_todos)
  - Autonomously decide when to search vs answer from context
  - Iterate: search → evaluate → refine → search again if needed
  - Stream token-by-token via LangGraph's message streaming

The only custom tool is `search_papers` for vector DB retrieval.
"""

from __future__ import annotations

import json
import logging
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
# System prompt
# ============================================================================

SYSTEM_PROMPT = """\
You are **OpenTA Agent**, an expert research assistant for the Telkom University \
academic paper catalog.

## Capabilities
You have access to a `search_papers` tool that searches a vector database of \
Telkom University research papers (theses, dissertations, journals, etc.).

## How You Work

### 1. Decide If a Search Is Needed
- **Search IS needed** when the user asks about research topics, papers, \
academic work, or anything that requires looking up actual papers.
- **Search is NOT needed** when the user:
  - Says hello or engages in casual conversation
  - Asks a follow-up question about papers already discussed in the conversation
  - Asks a general knowledge question unrelated to papers
  - Asks you to summarize, compare, or analyze papers already in context

### 2. For Research Queries — Be Thorough
- Use `write_todos` to plan multi-step research when the query is complex \
(e.g. "Compare ML approaches in IoT security papers").
- Call `search_papers` with specific, targeted queries. You can (and should) \
call it **multiple times** with different keywords to get comprehensive coverage.
- After searching, evaluate if you have enough information. If not, refine \
your query and search again.

### 3. Answering
- Provide **detailed, structured answers** with clear headings and bullet points.
- **Always cite papers** using inline `[N]` notation where N is the paper number \
from the search results (starting from 1).
- At the end, include a brief summary of key findings.
- If no papers are found, be honest and suggest alternative search terms.

### 4. Language
- Match the user's language. If they write in Indonesian, respond in Indonesian.
- Default to English if unclear.

## Citation Rules
- Every factual claim from a paper MUST have an inline citation like [1], [2], etc.
- The number corresponds to the paper's position in the search results.
- If you make multiple searches, number papers sequentially across all searches.
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
    """

    def __init__(
        self,
        retriever: PaperRetriever | None = None,
        model_name: str | None = None,
    ):
        self.retriever = retriever or PaperRetriever()
        self.settings = get_settings()
        self.model_name = model_name or self.settings.DSPY_MODEL

        # Tool (created once, stateless)
        self._search_tool = _create_search_papers_tool(self.retriever)

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
            max_tokens=4096,
        )

        self._agent = create_deep_agent(
            model=model,
            tools=[self._search_tool],
            system_prompt=SYSTEM_PROMPT,
        )

        logger.info("[DEEP-AGENTS] Agent created successfully")
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
            result = await agent.ainvoke({"messages": messages})
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
    # Streaming chat
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
        """Stream the Deep Agent response as SSE events.

        Uses ``stream_mode="messages"`` which yields ``(message_chunk, metadata)``
        tuples for token-level streaming.
        """
        agent = self._get_agent()
        messages = self._build_messages(
            question, history, language, catalog_type, year_from, year_to, author
        )

        # -- Emit start ------------------------------------------------
        yield format_sse(
            {"type": "start", "message": "Starting research...", "question": question}
        )

        # Accumulators
        final_answer = ""
        all_collected_messages: list = []
        current_tool_name: str | None = None
        search_query: str | None = None
        search_query_args: str = ""  # accumulate tool call arg chunks

        try:
            async for chunk, metadata in agent.astream(
                {"messages": messages},
                stream_mode="messages",
            ):
                node = metadata.get("langgraph_node", "")

                # We only care about messages from the model node and tools node
                if node not in ("model", "agent", "tools"):
                    continue

                # -- ToolMessage: search results from tool execution ----
                if isinstance(chunk, ToolMessage):
                    all_collected_messages.append(chunk)
                    if chunk.name == "search_papers":
                        yield format_sse(
                            {
                                "type": "tool_result",
                                "tool": "search_papers",
                                "content": "Search completed",
                            }
                        )
                    continue

                # -- AIMessageChunk: streaming tokens from the LLM ------
                if isinstance(chunk, (AIMessageChunk, AIMessage)):
                    # Collect full messages for source extraction later
                    if isinstance(chunk, AIMessage) and not isinstance(chunk, AIMessageChunk):
                        all_collected_messages.append(chunk)
                        continue

                    # Tool call chunks (the LLM is deciding to call a tool)
                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        for tc_chunk in chunk.tool_call_chunks:
                            tool_name = tc_chunk.get("name")
                            if tool_name and tool_name != current_tool_name:
                                current_tool_name = tool_name
                                search_query_args = ""  # reset for new tool call
                                yield format_sse(
                                    {
                                        "type": "tool_call",
                                        "tool": tool_name,
                                        "message": f"Calling {tool_name}...",
                                    }
                                )
                            # Accumulate args to extract search query
                            args_chunk = tc_chunk.get("args", "")
                            if args_chunk and current_tool_name == "search_papers":
                                search_query_args += args_chunk
                        continue

                    # Regular text content tokens
                    content = chunk.content if hasattr(chunk, "content") else ""
                    if content:
                        final_answer += content
                        yield format_sse({"type": "token", "content": content})

        except Exception as e:
            logger.error("[DEEP-AGENTS] Stream error: %s", e, exc_info=True)
            yield format_sse({"type": "error", "content": str(e)})
            yield "data: [DONE]\n\n"
            return

        # -- Post-stream: extract sources from collected messages -------
        sources, _ = _extract_sources_from_messages(all_collected_messages)

        # Extract search_query from accumulated tool call args
        if not search_query and search_query_args:
            try:
                args_data = json.loads(search_query_args)
                search_query = args_data.get("query")
            except (json.JSONDecodeError, TypeError):
                pass

        # Citation audit
        if sources:
            audit = _audit_citations(final_answer, sources)
            yield format_sse({"type": "citation_audit", **audit})

        # Sources event (for UI to build the reference list)
        if sources:
            yield format_sse(
                {
                    "type": "sources",
                    "sources": [s.model_dump() for s in sources],
                }
            )

        # Done event
        yield format_sse(
            {
                "type": "done",
                "content": final_answer,
                "sources": [s.model_dump() for s in sources],
            }
        )

        # -- Callbacks -------------------------------------------------
        if on_complete:
            try:
                # Serialize CitedPaper objects to dicts for JSON storage
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
