"""Database tools exposed via MCP for the AI agent."""

import re
from dataclasses import dataclass
from typing import Any, Optional

import sqlglot
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.schema_registry import (
    get_db_summary,
    get_all_domains,
    build_schema_context,
    SchemaContext,
)

logger = structlog.get_logger(__name__)


class SQLValidationError(Exception):
    """Raised when SQL validation fails."""
    pass


@dataclass
class ToolResponse:
    """Response from a database tool."""
    success: bool
    data: Optional[list[dict[str, Any]]] = None
    error: Optional[str] = None
    row_count: int = 0
    metadata: Optional[dict[str, Any]] = None


@dataclass
class QueryResult:
    """Result of a database query."""
    data: list[dict[str, Any]]
    row_count: int
    metadata: Optional[dict[str, Any]] = None


class SQLValidator:
    """
    Validates SQL queries for safety.
    
    Only SELECT statements are allowed. All DDL, DML, and dangerous
    operations are rejected.
    """
    
    # Forbidden SQL keywords/operations
    FORBIDDEN_KEYWORDS = {
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
        "GRANT", "REVOKE", "EXECUTE", "EXEC", "CALL", "INTO",  # INTO for SELECT INTO
        "COPY", "VACUUM", "ANALYZE", "CLUSTER", "REINDEX",
        "SET", "RESET", "SHOW",  # Session manipulation
        "LOCK", "UNLOCK",
        "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT",  # Transaction control
        "NOTIFY", "LISTEN", "UNLISTEN",  # Pub/sub
        "LOAD", "UNLOAD",
        "EXPLAIN",  # Can reveal query plans
    }

    # Forbidden functions that could be dangerous
    FORBIDDEN_FUNCTIONS = {
        "pg_sleep", "pg_terminate_backend", "pg_cancel_backend",
        "pg_read_file", "pg_read_binary_file", "pg_write_file",
        "lo_import", "lo_export",
        "dblink", "dblink_exec",
    }

    @classmethod
    def validate(cls, sql: str) -> tuple[bool, Optional[str]]:
        """
        Validate a SQL query for safety.
        
        Args:
            sql: The SQL query to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for empty query
        if not sql or not sql.strip():
            return False, "Empty query"
        
        try:
            # Check for SELECT INTO pattern first (before parsing)
            sql_upper = sql.upper()
            if re.search(r'\bSELECT\b.*\bINTO\b', sql_upper):
                return False, "SELECT INTO is not allowed"
            
            # Parse with sqlglot
            parsed = sqlglot.parse(sql, dialect="postgres")
            
            if not parsed:
                return False, "Failed to parse SQL query"
            
            for statement in parsed:
                # Check if it's a SELECT statement
                if statement is None:
                    continue
                    
                statement_type = type(statement).__name__
                if statement_type not in ("Select", "Union", "Intersect", "Except"):
                    return False, f"Only SELECT queries are allowed, got: {statement_type}"
                
                # Check for forbidden keywords
                for keyword in cls.FORBIDDEN_KEYWORDS:
                    if keyword == "INTO":
                        continue  # Already handled above
                    # Check for keyword as a word boundary
                    if re.search(rf'\b{keyword}\b', sql_upper):
                        return False, f"Forbidden keyword detected: {keyword}"
                
                # Check for forbidden functions
                for func in cls.FORBIDDEN_FUNCTIONS:
                    if func.lower() in sql.lower():
                        return False, f"Forbidden function detected: {func}"
            
            return True, None
            
        except Exception as e:
            logger.warning("SQL parsing error", error=str(e), sql=sql[:100])
            return False, f"SQL parsing error: {str(e)}"

    @classmethod
    def sanitize_identifier(cls, identifier: str) -> str:
        """Sanitize a SQL identifier (table name, column name)."""
        return re.sub(r'[^a-zA-Z0-9_]', '', identifier)

    @classmethod
    def add_limit_if_missing(cls, sql: str, limit: int = 1000) -> str:
        """Add LIMIT clause if not present."""
        if "LIMIT" not in sql.upper():
            sql = f"{sql.rstrip(';')} LIMIT {limit}"
        return sql


class DatabaseTools:
    """
    Database tools for the AI agent.
    
    Provides:
    - Schema information retrieval (summary and detailed)
    - Safe SQL query execution with validation
    - Dynamic context building for cost-efficient queries
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize database tools.
        
        Args:
            session: Async database session (should be read-only)
        """
        self.session = session
        self.validator = SQLValidator

    async def get_db_summary(self) -> ToolResponse:
        """
        Get a compact database summary.
        
        Returns a token-efficient overview of the database structure
        for initial context before table selection.
        
        Returns:
            ToolResponse with database summary
        """
        try:
            summary = get_db_summary()
            return ToolResponse(
                success=True,
                data=[{"summary": summary}],
                row_count=1,
                metadata={
                    "type": "db_summary",
                    "domains": get_all_domains(),
                },
            )
        except Exception as e:
            logger.error("Failed to get DB summary", error=str(e))
            return ToolResponse(success=False, error=str(e))

    async def get_schema_for_domains(
        self,
        domains: list[str],
    ) -> ToolResponse:
        """
        Get detailed schema for specific domains.
        
        Only loads schema for requested domains, minimizing token usage.
        
        Args:
            domains: List of domain names (e.g., ["projects", "budgets"])
            
        Returns:
            ToolResponse with schema context
        """
        try:
            context = build_schema_context(domains)
            return ToolResponse(
                success=True,
                data=[{
                    "schema_context": context.full_context,
                    "selected_domains": context.selected_domains,
                    "token_estimate": context.token_estimate,
                }],
                row_count=1,
                metadata={
                    "type": "domain_schema",
                    "domains": domains,
                    "token_estimate": context.token_estimate,
                },
            )
        except Exception as e:
            logger.error("Failed to get domain schema", error=str(e), domains=domains)
            return ToolResponse(success=False, error=str(e))

    async def get_live_table_stats(self) -> ToolResponse:
        """
        Get live statistics about database tables.
        
        Fetches actual row counts and table sizes from the database.
        Useful for understanding data distribution.
        
        Returns:
            ToolResponse with table statistics
        """
        try:
            query = text("""
                SELECT 
                    t.table_name,
                    (SELECT COUNT(*) FROM information_schema.columns c 
                     WHERE c.table_name = t.table_name AND c.table_schema = 'public') as column_count
                FROM information_schema.tables t
                WHERE t.table_schema = 'public' 
                AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_name
            """)
            
            result = await self.session.execute(query)
            rows = result.mappings().all()
            
            return ToolResponse(
                success=True,
                data=[dict(row) for row in rows],
                row_count=len(rows),
                metadata={"type": "table_stats"},
            )
        except Exception as e:
            logger.error("Failed to get table stats", error=str(e))
            return ToolResponse(success=False, error=str(e))

    async def get_table_columns(
        self,
        table_names: list[str],
    ) -> ToolResponse:
        """
        Get column information for specific tables.
        
        Fetches column details directly from the database schema.
        
        Args:
            table_names: List of table names to get columns for
            
        Returns:
            ToolResponse with column information
        """
        try:
            # Sanitize table names
            safe_names = [self.validator.sanitize_identifier(t) for t in table_names]
            
            query = text("""
                SELECT 
                    c.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    tc.constraint_type
                FROM information_schema.columns c
                LEFT JOIN information_schema.key_column_usage kcu 
                    ON kcu.table_name = c.table_name 
                    AND kcu.column_name = c.column_name
                    AND kcu.table_schema = c.table_schema
                LEFT JOIN information_schema.table_constraints tc 
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = c.table_schema
                WHERE c.table_schema = 'public'
                AND c.table_name = ANY(:table_names)
                ORDER BY c.table_name, c.ordinal_position
            """)
            
            result = await self.session.execute(query, {"table_names": safe_names})
            rows = result.mappings().all()
            
            return ToolResponse(
                success=True,
                data=[dict(row) for row in rows],
                row_count=len(rows),
                metadata={
                    "type": "table_columns",
                    "tables": table_names,
                },
            )
        except Exception as e:
            logger.error("Failed to get table columns", error=str(e))
            return ToolResponse(success=False, error=str(e))

    async def execute_query(
        self,
        sql: str,
        limit: int = 1000,
    ) -> ToolResponse:
        """
        Execute a validated SQL SELECT query.
        
        The query must pass safety validation before execution.
        
        Args:
            sql: The SQL query to execute
            limit: Maximum number of results (default 1000)
            
        Returns:
            ToolResponse with query results
        """
        # Validate the SQL
        is_valid, error = self.validator.validate(sql)
        if not is_valid:
            logger.warning("SQL validation failed", error=error, sql=sql[:200])
            return ToolResponse(
                success=False,
                error=f"SQL validation failed: {error}",
                metadata={"validation_error": True},
            )

        # Add LIMIT if missing
        sql = self.validator.add_limit_if_missing(sql, limit)

        try:
            logger.info("Executing query", sql_preview=sql[:100])
            result = await self.session.execute(text(sql))
            rows = result.mappings().all()
            
            return ToolResponse(
                success=True,
                data=[dict(row) for row in rows],
                row_count=len(rows),
                metadata={"type": "query_result"},
            )
        except Exception as e:
            logger.error("Query execution failed", error=str(e), sql=sql[:200])
            return ToolResponse(
                success=False,
                error=f"Query execution failed: {str(e)}",
            )

    async def get_sample_data(
        self,
        table_name: str,
        limit: int = 5,
    ) -> ToolResponse:
        """
        Get sample data from a table.
        
        Useful for understanding data structure and values.
        
        Args:
            table_name: Name of the table
            limit: Number of sample rows (default 5)
            
        Returns:
            ToolResponse with sample data
        """
        # Sanitize table name
        safe_name = self.validator.sanitize_identifier(table_name)
        
        # Validate it's a known table (basic check)
        sql = f'SELECT * FROM "{safe_name}" LIMIT {min(limit, 10)}'
        
        return await self.execute_query(sql, limit=min(limit, 10))

    def get_tool_descriptions(self) -> list[dict[str, Any]]:
        """
        Get descriptions of all available tools for MCP registration.
        
        Returns:
            List of tool description dictionaries
        """
        return [
            {
                "name": "get_db_summary",
                "description": "Get a compact summary of the database structure and available domains. "
                               "Use this first to understand what data is available.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_schema_for_domains",
                "description": "Get detailed schema for specific domains. Only request domains you need "
                               "to minimize context size. Common domains: projects, budgets, accounts, actuals.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of domain names to get schema for",
                        },
                    },
                    "required": ["domains"],
                },
            },
            {
                "name": "get_table_columns",
                "description": "Get column information for specific tables directly from the database.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of table names",
                        },
                    },
                    "required": ["table_names"],
                },
            },
            {
                "name": "execute_query",
                "description": "Execute a SQL SELECT query. The query must be read-only and pass validation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "The SQL SELECT query to execute",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default 1000)",
                            "default": 1000,
                        },
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "get_sample_data",
                "description": "Get sample rows from a table to understand data structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the table",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of sample rows (max 10)",
                            "default": 5,
                        },
                    },
                    "required": ["table_name"],
                },
            },
        ]
