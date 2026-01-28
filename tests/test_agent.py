"""Tests for LangGraph agent."""

import pytest
from datetime import datetime

from src.agent.state import (
    AgentState,
    Message,
    create_initial_state,
    add_assistant_message,
    format_conversation_history,
)
from src.agent.routing import (
    route_after_classification,
    route_after_sql_validation,
    route_after_query_execution,
)


class TestAgentState:
    """Tests for AgentState and helper functions."""
    
    def test_create_initial_state(self):
        """Test initial state creation."""
        state = create_initial_state(
            user_message="What is the budget?",
            user_id="test-user",
        )
        
        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][0]["content"] == "What is the budget?"
        assert state["user_id"] == "test-user"
        assert state["session_id"] is not None
        assert state["intent"] == ""
        assert state["generated_sql"] is None
        assert state["total_llm_calls"] == 0
        # New fields for dynamic schema
        assert state["selected_domains"] is None
        assert state["schema_context"] is None
    
    def test_create_initial_state_with_session(self):
        """Test initial state with provided session ID."""
        state = create_initial_state(
            user_message="Test",
            session_id="custom-session-123",
        )
        
        assert state["session_id"] == "custom-session-123"
    
    def test_add_assistant_message(self):
        """Test adding assistant message."""
        state = create_initial_state("Test")
        update = add_assistant_message(state, "Response content")
        
        assert "messages" in update
        assert len(update["messages"]) == 1
        assert update["messages"][0]["role"] == "assistant"
        assert update["messages"][0]["content"] == "Response content"
    
    def test_format_conversation_history(self):
        """Test conversation history formatting."""
        messages = [
            Message(role="user", content="Question 1", timestamp=None, metadata=None),
            Message(role="assistant", content="Answer 1", timestamp=None, metadata=None),
            Message(role="user", content="Question 2", timestamp=None, metadata=None),
        ]
        
        history = format_conversation_history(messages)
        
        assert "User: Question 1" in history
        assert "Assistant: Answer 1" in history
        assert "User: Question 2" in history
    
    def test_format_conversation_history_limit(self):
        """Test conversation history respects limit."""
        messages = [
            Message(role="user", content=f"Message {i}", timestamp=None, metadata=None)
            for i in range(20)
        ]
        
        history = format_conversation_history(messages, max_messages=5)
        
        # Should only include last 5 messages
        assert "Message 15" in history
        assert "Message 19" in history
        assert "Message 10" not in history


class TestRouting:
    """Tests for routing functions."""
    
    def test_route_to_table_selection(self):
        """Test routing to table selection for db_query intent."""
        state = create_initial_state("Test")
        state["intent"] = "db_query"
        state["requires_db_query"] = True
        
        next_node = route_after_classification(state)
        assert next_node == "select_tables"  # Now routes to table selection first
    
    def test_route_to_clarification(self):
        """Test routing to clarification."""
        state = create_initial_state("Test")
        state["intent"] = "clarify"
        state["clarification_needed"] = True
        
        next_node = route_after_classification(state)
        assert next_node == "handle_clarification"
    
    def test_route_to_general_info(self):
        """Test routing to general info."""
        state = create_initial_state("Test")
        state["intent"] = "general_info"
        state["requires_db_query"] = False
        
        next_node = route_after_classification(state)
        assert next_node == "handle_general_info"
    
    def test_route_after_valid_sql(self):
        """Test routing after valid SQL."""
        state = create_initial_state("Test")
        state["sql_validation_error"] = None
        state["sql_retry_count"] = 0
        
        next_node = route_after_sql_validation(state)
        assert next_node == "execute_query"
    
    def test_route_after_invalid_sql_retry(self):
        """Test routing to retry after invalid SQL."""
        state = create_initial_state("Test")
        state["sql_validation_error"] = "Invalid syntax"
        state["sql_retry_count"] = 1
        
        next_node = route_after_sql_validation(state)
        assert next_node == "generate_sql"
    
    def test_route_after_max_retries(self):
        """Test routing to error after max retries."""
        state = create_initial_state("Test")
        state["sql_validation_error"] = "Invalid syntax"
        state["sql_retry_count"] = 5  # Exceeds max
        
        next_node = route_after_sql_validation(state)
        assert next_node == "handle_error"
    
    def test_route_after_successful_query(self):
        """Test routing after successful query."""
        state = create_initial_state("Test")
        state["query_error"] = None
        
        next_node = route_after_query_execution(state)
        assert next_node == "analyze_results"
    
    def test_route_after_query_error_retry(self):
        """Test routing to retry after query error."""
        state = create_initial_state("Test")
        state["query_error"] = "Connection timeout"
        state["sql_retry_count"] = 1
        
        next_node = route_after_query_execution(state)
        assert next_node == "generate_sql"


class TestTableSelectionRouting:
    """Tests for new table selection routing."""
    
    def test_default_routes_to_table_selection(self):
        """Test that db queries route to table selection first."""
        state = create_initial_state("What is the total budget?")
        state["intent"] = "db_query"
        
        next_node = route_after_classification(state)
        assert next_node == "select_tables"
    
    def test_empty_intent_routes_to_table_selection(self):
        """Test that empty intent defaults to table selection."""
        state = create_initial_state("Test query")
        state["intent"] = ""
        
        next_node = route_after_classification(state)
        assert next_node == "select_tables"
