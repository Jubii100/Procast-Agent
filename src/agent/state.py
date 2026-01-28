"""Agent state definitions for LangGraph."""

from dataclasses import dataclass, field
from typing import Annotated, Any, Optional, TypedDict
import operator
from datetime import datetime


class Message(TypedDict):
    """A message in the conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: Optional[str]
    metadata: Optional[dict[str, Any]]


class AgentState(TypedDict):
    """
    State for the Procast AI agent.
    
    This state is passed through all nodes in the LangGraph workflow.
    It tracks conversation history, intermediate results, and metadata.
    """
    
    # Conversation
    messages: Annotated[list[Message], operator.add]
    
    # User context (for future JWT integration)
    user_id: str
    session_id: str
    
    # Intent classification
    intent: str  # "db_query", "clarify", "general_info"
    requires_db_query: bool
    clarification_needed: bool
    clarification_questions: Optional[str]
    
    # Schema selection (NEW - for cost-efficient context)
    selected_domains: Optional[list[str]]
    schema_context: Optional[str]
    domain_selection_reasoning: Optional[str]
    
    # SQL generation
    generated_sql: Optional[str]
    sql_explanation: Optional[str]
    sql_validation_error: Optional[str]
    sql_retry_count: int
    
    # Query execution
    query_results: Optional[list[dict[str, Any]]]
    query_row_count: int
    query_error: Optional[str]
    
    # Analysis
    analysis: Optional[str]
    recommendations: Optional[str]
    confidence: float
    
    # Final response
    response: Optional[str]
    
    # Error handling
    error: Optional[str]
    error_type: Optional[str]
    
    # Metadata
    processing_started: Optional[str]
    processing_completed: Optional[str]
    total_llm_calls: int
    total_db_queries: int


def create_initial_state(
    user_message: str,
    user_id: str = "anonymous",
    session_id: Optional[str] = None,
) -> AgentState:
    """
    Create an initial agent state for a new query.
    
    Args:
        user_message: The user's question or request
        user_id: User identifier (for JWT integration)
        session_id: Session identifier (auto-generated if not provided)
        
    Returns:
        Initialized AgentState
    """
    import uuid
    
    session_id = session_id or str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat()
    
    return AgentState(
        messages=[
            Message(
                role="user",
                content=user_message,
                timestamp=timestamp,
                metadata=None,
            )
        ],
        user_id=user_id,
        session_id=session_id,
        intent="",
        requires_db_query=False,
        clarification_needed=False,
        clarification_questions=None,
        # Schema selection
        selected_domains=None,
        schema_context=None,
        domain_selection_reasoning=None,
        # SQL generation
        generated_sql=None,
        sql_explanation=None,
        sql_validation_error=None,
        sql_retry_count=0,
        query_results=None,
        query_row_count=0,
        query_error=None,
        analysis=None,
        recommendations=None,
        confidence=0.0,
        response=None,
        error=None,
        error_type=None,
        processing_started=timestamp,
        processing_completed=None,
        total_llm_calls=0,
        total_db_queries=0,
    )


def add_assistant_message(state: AgentState, content: str) -> dict:
    """
    Add an assistant message to the state.
    
    Args:
        state: Current agent state
        content: Message content
        
    Returns:
        State update dict with the new message
    """
    return {
        "messages": [
            Message(
                role="assistant",
                content=content,
                timestamp=datetime.utcnow().isoformat(),
                metadata=None,
            )
        ]
    }


def format_conversation_history(messages: list[Message], max_messages: int = 10) -> str:
    """
    Format conversation history for context.
    
    Args:
        messages: List of messages
        max_messages: Maximum messages to include
        
    Returns:
        Formatted conversation string
    """
    recent_messages = messages[-max_messages:]
    
    formatted = []
    for msg in recent_messages:
        role = msg["role"].capitalize()
        content = msg["content"]
        formatted.append(f"{role}: {content}")
    
    return "\n".join(formatted)
