"""Routing logic for LangGraph conditional edges."""

from typing import Literal

import structlog

from src.agent.state import AgentState
from src.core.config import settings

logger = structlog.get_logger(__name__)

# Maximum SQL retry attempts
MAX_SQL_RETRIES = 3


def route_after_classification(
    state: AgentState,
) -> Literal["select_tables", "handle_clarification", "handle_general_info"]:
    """
    Route based on intent classification.
    
    For db_query intent, routes to select_tables first (cost-efficient schema loading).
    
    Args:
        state: Current agent state
        
    Returns:
        Next node name
    """
    intent = state.get("intent", "db_query")
    
    logger.debug("Routing after classification", intent=intent)
    
    if intent == "clarify" or state.get("clarification_needed"):
        return "handle_clarification"
    elif intent == "general_info" and not state.get("requires_db_query"):
        return "handle_general_info"
    else:
        # Route to table selection first for cost-efficient schema loading
        return "select_tables"


def route_after_sql_validation(
    state: AgentState,
) -> Literal["execute_query", "generate_sql", "handle_error"]:
    """
    Route based on SQL validation result.
    
    Args:
        state: Current agent state
        
    Returns:
        Next node name
    """
    validation_error = state.get("sql_validation_error")
    retry_count = state.get("sql_retry_count", 0)
    
    logger.debug(
        "Routing after SQL validation",
        has_error=bool(validation_error),
        retry_count=retry_count,
    )
    
    if not validation_error:
        # Validation passed
        return "execute_query"
    elif retry_count < MAX_SQL_RETRIES:
        # Retry SQL generation (schema context is already loaded)
        logger.info("Retrying SQL generation", attempt=retry_count + 1)
        return "generate_sql"
    else:
        # Max retries exceeded
        logger.warning("Max SQL retries exceeded")
        return "handle_error"


def route_after_query_execution(
    state: AgentState,
) -> Literal["analyze_results", "generate_sql", "handle_error"]:
    """
    Route based on query execution result.
    
    Args:
        state: Current agent state
        
    Returns:
        Next node name
    """
    query_error = state.get("query_error")
    retry_count = state.get("sql_retry_count", 0)
    
    logger.debug(
        "Routing after query execution",
        has_error=bool(query_error),
        retry_count=retry_count,
    )
    
    if not query_error:
        # Query succeeded
        return "analyze_results"
    elif retry_count < MAX_SQL_RETRIES:
        # The error might be due to bad SQL, retry generation
        logger.info("Query failed, retrying SQL generation", attempt=retry_count + 1)
        return "generate_sql"
    else:
        # Max retries exceeded
        logger.warning("Max query retries exceeded")
        return "handle_error"


def should_continue_or_end(
    state: AgentState,
) -> Literal["continue", "end"]:
    """
    Determine if the workflow should continue or end.
    
    Args:
        state: Current agent state
        
    Returns:
        "continue" or "end"
    """
    # Check for errors that should end the workflow
    if state.get("error") and state.get("error_type") not in ("sql_generation", "query_execution"):
        return "end"
    
    # Check if we have a response
    if state.get("response"):
        return "end"
    
    return "continue"


def check_confidence_threshold(
    state: AgentState,
) -> Literal["high_confidence", "low_confidence"]:
    """
    Check if analysis confidence meets threshold.
    
    Args:
        state: Current agent state
        
    Returns:
        Confidence level
    """
    confidence = state.get("confidence", 0.0)
    threshold = settings.min_confidence_threshold
    
    if confidence >= threshold:
        return "high_confidence"
    else:
        logger.info(
            "Low confidence analysis",
            confidence=confidence,
            threshold=threshold,
        )
        return "low_confidence"
