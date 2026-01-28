"""Tests for MCP server and tools."""

import pytest

from src.mcp.tools import SQLValidator, ToolResponse
from src.db.schema_registry import (
    get_db_summary,
    get_all_domains,
    get_domain_schema,
    build_schema_context,
)


class TestSQLValidator:
    """Tests for SQL validation."""
    
    def test_valid_select(self):
        """Test valid SELECT query passes."""
        sql = 'SELECT * FROM "Projects" WHERE "IsDisabled" = false'
        is_valid, error = SQLValidator.validate(sql)
        assert is_valid
        assert error is None
    
    def test_valid_select_with_join(self):
        """Test valid SELECT with JOIN passes."""
        sql = '''
            SELECT p."Brand", SUM(el."Amount")
            FROM "Projects" p
            JOIN "ProjectAccounts" pa ON pa."ProjectId" = p."Id"
            JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id"
            WHERE p."IsDisabled" = false
            GROUP BY p."Brand"
        '''
        is_valid, error = SQLValidator.validate(sql)
        assert is_valid
        assert error is None
    
    def test_rejects_insert(self):
        """Test INSERT is rejected."""
        sql = 'INSERT INTO "Projects" ("Brand") VALUES (\'Test\')'
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
        assert "INSERT" in error or "Only SELECT" in error
    
    def test_rejects_update(self):
        """Test UPDATE is rejected."""
        sql = 'UPDATE "Projects" SET "Brand" = \'Test\''
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
        assert "UPDATE" in error or "Only SELECT" in error
    
    def test_rejects_delete(self):
        """Test DELETE is rejected."""
        sql = 'DELETE FROM "Projects"'
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
        assert "DELETE" in error or "Only SELECT" in error
    
    def test_rejects_drop(self):
        """Test DROP is rejected."""
        sql = 'DROP TABLE "Projects"'
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
        assert "DROP" in error or "Only SELECT" in error
    
    def test_rejects_truncate(self):
        """Test TRUNCATE is rejected."""
        sql = 'TRUNCATE TABLE "Projects"'
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
    
    def test_rejects_dangerous_functions(self):
        """Test dangerous functions are rejected."""
        sql = "SELECT pg_sleep(10)"
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
        assert "pg_sleep" in error.lower()
    
    def test_rejects_empty_query(self):
        """Test empty query is rejected."""
        is_valid, error = SQLValidator.validate("")
        assert not is_valid
        assert error is not None
    
    def test_rejects_select_into(self):
        """Test SELECT INTO is rejected."""
        sql = 'SELECT * INTO "NewTable" FROM "Projects"'
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
    
    def test_sanitize_identifier(self):
        """Test identifier sanitization."""
        assert SQLValidator.sanitize_identifier("valid_name") == "valid_name"
        assert SQLValidator.sanitize_identifier("invalid;name") == "invalidname"
        assert SQLValidator.sanitize_identifier("drop--table") == "droptable"
    
    def test_add_limit_if_missing(self):
        """Test LIMIT clause addition."""
        sql = 'SELECT * FROM "Projects"'
        result = SQLValidator.add_limit_if_missing(sql, 100)
        assert "LIMIT 100" in result
        
        # Should not add if already present
        sql_with_limit = 'SELECT * FROM "Projects" LIMIT 50'
        result = SQLValidator.add_limit_if_missing(sql_with_limit, 100)
        assert "LIMIT 100" not in result
        assert "LIMIT 50" in result


class TestToolResponse:
    """Tests for ToolResponse model."""
    
    def test_success_response(self):
        """Test successful response creation."""
        response = ToolResponse(
            success=True,
            data=[{"id": 1, "name": "Test"}],
            row_count=1,
        )
        assert response.success
        assert len(response.data) == 1
        assert response.row_count == 1
        assert response.error is None
    
    def test_error_response(self):
        """Test error response creation."""
        response = ToolResponse(
            success=False,
            error="Database connection failed",
        )
        assert not response.success
        assert response.data is None
        assert response.error == "Database connection failed"


class TestSchemaRegistry:
    """Tests for schema registry functionality."""
    
    def test_get_db_summary(self):
        """Test database summary retrieval."""
        summary = get_db_summary()
        assert "PROCAST DATABASE" in summary
        assert "DOMAINS:" in summary
        assert "projects" in summary.lower() or "budgets" in summary.lower()
    
    def test_get_all_domains(self):
        """Test getting all domain names."""
        domains = get_all_domains()
        assert isinstance(domains, list)
        assert "projects" in domains
        assert "budgets" in domains
        assert "accounts" in domains
    
    def test_get_domain_schema(self):
        """Test getting schema for a specific domain."""
        schema = get_domain_schema("projects")
        assert "Projects" in schema
        assert "SubProjects" in schema or "ProjectAccounts" in schema
    
    def test_get_domain_schema_unknown(self):
        """Test getting schema for unknown domain returns empty."""
        schema = get_domain_schema("unknown_domain")
        assert schema == ""
    
    def test_build_schema_context(self):
        """Test building schema context for multiple domains."""
        context = build_schema_context(["projects", "budgets"])
        
        assert context.db_summary is not None
        assert context.selected_domains == ["projects", "budgets"]
        assert "Projects" in context.table_schemas
        assert "EntryLines" in context.table_schemas
        assert context.token_estimate > 0
    
    def test_schema_context_full_context(self):
        """Test full context property."""
        context = build_schema_context(["projects"])
        full = context.full_context
        
        assert context.db_summary in full
        assert context.table_schemas in full
        assert "KEY JOIN PATHS" in full or "relationships" in full.lower()
