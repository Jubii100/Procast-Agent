"""Tests for Row-Level Security (RLS) scope control."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.db.connection import DatabaseManager, lookup_person_by_email
from src.agent.state import create_initial_state, AgentState
from src.api.middleware.auth import UserContext


class TestUserContext:
    """Tests for UserContext with person_id/company_id."""

    def test_user_context_with_person_id(self):
        """Test UserContext includes person_id and company_id."""
        ctx = UserContext(
            user_id="user-123",
            email="test@example.com",
            person_id="person-uuid-123",
            company_id="company-uuid-456",
        )
        assert ctx.person_id == "person-uuid-123"
        assert ctx.company_id == "company-uuid-456"

    def test_user_context_default_scopes(self):
        """Test UserContext has default scopes."""
        ctx = UserContext(user_id="user-123")
        assert "budget:read" in ctx.scopes
        assert "budget:analyze" in ctx.scopes

    def test_user_context_has_scope(self):
        """Test has_scope method."""
        ctx = UserContext(
            user_id="user-123",
            scopes=["budget:read", "admin:write"],
        )
        assert ctx.has_scope("budget:read") is True
        assert ctx.has_scope("admin:write") is True
        assert ctx.has_scope("nonexistent") is False


class TestAgentState:
    """Tests for AgentState with user context."""

    def test_create_initial_state_with_email(self):
        """Test create_initial_state includes email and person_id."""
        state = create_initial_state(
            user_message="Test question",
            user_id="user-123",
            email="test@example.com",
            person_id="person-uuid-123",
            company_id="company-uuid-456",
        )
        
        assert state["email"] == "test@example.com"
        assert state["person_id"] == "person-uuid-123"
        assert state["company_id"] == "company-uuid-456"

    def test_create_initial_state_optional_fields(self):
        """Test create_initial_state with optional fields as None."""
        state = create_initial_state(
            user_message="Test question",
            user_id="user-123",
        )
        
        assert state["email"] is None
        assert state["person_id"] is None
        assert state["company_id"] is None


class TestDatabaseScoping:
    """Tests for database scoping functions."""

    @pytest.mark.asyncio
    async def test_lookup_person_by_email_found(self):
        """Test lookup_person_by_email when person exists."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {
            "person_id": "uuid-123",
            "company_id": "company-456",
            "email": "test@example.com",
        }
        mock_session.execute.return_value = mock_result

        result = await lookup_person_by_email(mock_session, "test@example.com")
        
        assert result is not None
        assert result["person_id"] == "uuid-123"
        assert result["company_id"] == "company-456"

    @pytest.mark.asyncio
    async def test_lookup_person_by_email_not_found(self):
        """Test lookup_person_by_email when person doesn't exist."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await lookup_person_by_email(mock_session, "nonexistent@example.com")
        
        assert result is None


class TestSQLValidatorWithAudit:
    """Tests for SQL validator with audit logging."""

    def test_extract_tables_from_sql(self):
        """Test table extraction for audit logging."""
        from src.mcp.tools import DatabaseTools
        
        # Create a mock session
        mock_session = MagicMock()
        tools = DatabaseTools(mock_session)
        
        sql = 'SELECT * FROM "Projects" p JOIN "EntryLines" e ON e."ProjectId" = p."Id"'
        tables = tools._extract_tables_from_sql(sql)
        
        assert "Projects" in tables
        assert "EntryLines" in tables

    def test_extract_tables_handles_errors(self):
        """Test table extraction handles invalid SQL gracefully."""
        from src.mcp.tools import DatabaseTools
        
        mock_session = MagicMock()
        tools = DatabaseTools(mock_session)
        
        # Invalid SQL should return empty list, not raise
        tables = tools._extract_tables_from_sql("NOT VALID SQL {{{{")
        assert tables == []


class TestRLSIntegration:
    """Integration tests for RLS (require database connection)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scoped_session_sets_person_id(self):
        """Test that scoped session sets the app.current_person_id variable."""
        # This test requires a real database connection
        # Skip if not available
        pytest.skip("Integration test - requires database connection")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rls_filters_projects_by_membership(self):
        """Test that RLS correctly filters projects by membership."""
        # This test requires a real database with RLS enabled
        pytest.skip("Integration test - requires database with RLS enabled")
