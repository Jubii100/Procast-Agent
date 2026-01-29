"""LangGraph workflow definition for Procast AI agent."""

from typing import Optional

import structlog
from langgraph.graph import END, StateGraph

from src.agent.state import AgentState, create_initial_state
from src.agent.nodes import (
    classify_intent_node,
    select_tables_node,
    generate_sql_node,
    validate_sql_node,
    execute_query_node,
    analyze_results_node,
    format_response_node,
    handle_clarification_node,
    handle_general_info_node,
    handle_error_node,
)
from src.agent.routing import (
    route_after_classification,
    route_after_sql_validation,
    route_after_query_execution,
)
from src.db.connection import DatabaseManager
from src.dspy_modules.config import (
    configure_claude,
    get_lm_usage_entries,
    get_lm_usage_snapshot,
    restore_lm_cache_state,
    set_lm_cache_enabled,
)

logger = structlog.get_logger(__name__)


def _extract_usage_counts(usage: dict) -> tuple[Optional[int], Optional[int], Optional[int]]:
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    if prompt_tokens is None:
        prompt_tokens = usage.get("input_tokens")
    if completion_tokens is None:
        completion_tokens = usage.get("output_tokens")

    total_tokens = usage.get("total_tokens")
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    return prompt_tokens, completion_tokens, total_tokens


def _log_lm_usage(entries: list[dict], session_id: Optional[str]) -> None:
    if not entries:
        logger.warning(
            "No SDK usage metadata captured for LLM calls",
            session_id=session_id,
        )
        return

    for entry in entries:
        usage = entry.get("usage") or {}
        prompt_tokens, completion_tokens, total_tokens = _extract_usage_counts(usage)
        logger.info(
            "LLM usage",
            session_id=session_id,
            model=entry.get("model"),
            lm_label=entry.get("lm_label"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=entry.get("cost"),
            cache_hit=entry.get("cache_hit"),
            usage=usage if not (prompt_tokens or completion_tokens or total_tokens) else None,
        )


def create_agent_graph() -> StateGraph:
    """
    Create the LangGraph workflow for the Procast AI agent.
    
    Workflow:
    1. Classify intent
    2. For db_query: Select relevant tables → Generate SQL → Validate → Execute → Analyze
    3. For clarify: Return clarification questions
    4. For general_info: Return system info
    
    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info("Creating agent graph")
    
    # Create the graph with AgentState
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("select_tables", select_tables_node)  # NEW: Dynamic table selection
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("validate_sql", validate_sql_node)
    workflow.add_node("execute_query", execute_query_node)
    workflow.add_node("analyze_results", analyze_results_node)
    workflow.add_node("format_response", format_response_node)
    workflow.add_node("handle_clarification", handle_clarification_node)
    workflow.add_node("handle_general_info", handle_general_info_node)
    workflow.add_node("handle_error", handle_error_node)
    
    # Set entry point
    workflow.set_entry_point("classify_intent")
    
    # Add edges from classification
    workflow.add_conditional_edges(
        "classify_intent",
        route_after_classification,
        {
            "select_tables": "select_tables",  # Route to table selection first
            "handle_clarification": "handle_clarification",
            "handle_general_info": "handle_general_info",
        }
    )
    
    # Table selection → SQL generation
    workflow.add_edge("select_tables", "generate_sql")
    
    # SQL generation → validation
    workflow.add_edge("generate_sql", "validate_sql")
    
    # Validation routing
    workflow.add_conditional_edges(
        "validate_sql",
        route_after_sql_validation,
        {
            "execute_query": "execute_query",
            "generate_sql": "generate_sql",  # Retry with same schema context
            "handle_error": "handle_error",
        }
    )
    
    # Query execution routing
    workflow.add_conditional_edges(
        "execute_query",
        route_after_query_execution,
        {
            "analyze_results": "analyze_results",
            "generate_sql": "generate_sql",  # Retry
            "handle_error": "handle_error",
        }
    )
    
    # Analysis → format response
    workflow.add_edge("analyze_results", "format_response")
    
    # Terminal edges
    workflow.add_edge("format_response", END)
    workflow.add_edge("handle_clarification", END)
    workflow.add_edge("handle_general_info", END)
    workflow.add_edge("handle_error", END)
    
    # Compile and return
    return workflow.compile()


class ProcastAgent:
    """
    High-level interface for the Procast AI agent.
    
    Handles initialization, configuration, and provides a simple
    interface for running queries.
    """

    def __init__(self):
        """Initialize the agent."""
        self._graph: Optional[StateGraph] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the agent.
        
        Sets up database connection and configures the LLM.
        """
        if self._initialized:
            return
        
        logger.info("Initializing Procast Agent")
        
        # Initialize database
        await DatabaseManager.initialize(use_readonly=True)
        
        # Configure Claude for DSPy
        configure_claude()
        
        # Create the graph
        self._graph = create_agent_graph()
        
        self._initialized = True
        logger.info("Procast Agent initialized")

    async def close(self) -> None:
        """Close the agent and release resources."""
        logger.info("Closing Procast Agent")
        await DatabaseManager.close()
        self._initialized = False

    async def query(
        self,
        question: str,
        user_id: str = "anonymous",
        session_id: Optional[str] = None,
        use_cache: Optional[bool] = None,
    ) -> dict:
        """
        Run a query through the agent.
        
        Args:
            question: The user's question
            user_id: User identifier
            session_id: Session identifier
            use_cache: Override LLM caching for this query (True/False)
            
        Returns:
            Dictionary with response and metadata
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(
            "Processing query",
            question=question[:100],
            user_id=user_id,
            use_cache=use_cache,
        )
        
        # Create initial state
        initial_state = create_initial_state(
            user_message=question,
            user_id=user_id,
            session_id=session_id,
        )

        cache_state = None
        if use_cache is not None:
            cache_state = set_lm_cache_enabled(use_cache, initialize=True)

        usage_snapshot = get_lm_usage_snapshot()
        
        # Run the graph
        try:
            final_state = await self._graph.ainvoke(initial_state)
        finally:
            if cache_state is not None:
                restore_lm_cache_state(cache_state)

        _log_lm_usage(get_lm_usage_entries(usage_snapshot), final_state.get("session_id"))
        
        logger.info(
            "Query completed",
            session_id=final_state.get("session_id"),
            confidence=final_state.get("confidence"),
            llm_calls=final_state.get("total_llm_calls"),
            db_queries=final_state.get("total_db_queries"),
            domains_used=final_state.get("selected_domains"),
        )
        
        # Return structured response
        return {
            "response": final_state.get("response", ""),
            "analysis": final_state.get("analysis"),
            "recommendations": final_state.get("recommendations"),
            "confidence": final_state.get("confidence", 0.0),
            "data": final_state.get("query_results"),
            "row_count": final_state.get("query_row_count", 0),
            "sql_query": final_state.get("generated_sql"),
            "sql_explanation": final_state.get("sql_explanation"),
            "session_id": final_state.get("session_id"),
            "error": final_state.get("error"),
            "metadata": {
                "intent": final_state.get("intent"),
                "selected_domains": final_state.get("selected_domains"),
                "domain_selection_reasoning": final_state.get("domain_selection_reasoning"),
                "total_llm_calls": final_state.get("total_llm_calls", 0),
                "total_db_queries": final_state.get("total_db_queries", 0),
                "processing_started": final_state.get("processing_started"),
                "processing_completed": final_state.get("processing_completed"),
            },
        }

    async def health_check(self) -> dict:
        """
        Check agent health status.
        
        Returns:
            Health status dictionary
        """
        db_health = await DatabaseManager.health_check()
        
        return {
            "agent_initialized": self._initialized,
            "database": db_health,
            "status": "healthy" if self._initialized and db_health["status"] == "healthy" else "unhealthy",
        }


# Global agent instance
_agent: Optional[ProcastAgent] = None


async def get_agent() -> ProcastAgent:
    """
    Get the global agent instance.
    
    Returns:
        Initialized ProcastAgent
    """
    global _agent
    
    if _agent is None:
        _agent = ProcastAgent()
        await _agent.initialize()
    
    return _agent
