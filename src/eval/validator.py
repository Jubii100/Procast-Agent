"""Validation utilities for SQL and results."""

import re
from typing import Any, Optional

import sqlglot
import structlog
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger(__name__)


class SQLValidator:
    """
    Validates SQL queries for safety and correctness.
    
    Ensures only SELECT statements are executed and blocks
    potentially dangerous operations.
    """
    
    # Forbidden SQL operations
    FORBIDDEN_KEYWORDS = {
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
        "GRANT", "REVOKE", "EXECUTE", "EXEC", "CALL",
        "COPY", "VACUUM", "ANALYZE", "CLUSTER", "REINDEX",
        "SET", "RESET", "SHOW",
        "LOCK", "UNLOCK",
        "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT",
        "NOTIFY", "LISTEN", "UNLISTEN",
        "LOAD", "UNLOAD",
    }
    
    # Forbidden functions
    FORBIDDEN_FUNCTIONS = {
        "pg_sleep", "pg_terminate_backend", "pg_cancel_backend",
        "pg_read_file", "pg_read_binary_file", "pg_write_file",
        "lo_import", "lo_export",
        "dblink", "dblink_exec",
    }
    
    # Maximum query length
    MAX_QUERY_LENGTH = 10000
    
    @classmethod
    def validate(cls, sql: str) -> tuple[bool, Optional[str]]:
        """
        Validate a SQL query.
        
        Args:
            sql: The SQL query to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not sql or not sql.strip():
            return False, "Empty SQL query"
        
        sql = sql.strip()
        
        # Check length
        if len(sql) > cls.MAX_QUERY_LENGTH:
            return False, f"Query too long (max {cls.MAX_QUERY_LENGTH} chars)"
        
        try:
            # Parse with sqlglot
            statements = sqlglot.parse(sql, dialect="postgres")
            
            if not statements:
                return False, "Failed to parse SQL"
            
            for statement in statements:
                if statement is None:
                    continue
                
                # Check statement type
                stmt_type = type(statement).__name__
                if stmt_type not in ("Select", "Union", "Intersect", "Except", "Subquery"):
                    return False, f"Only SELECT statements allowed, got: {stmt_type}"
            
            # Check for forbidden keywords
            sql_upper = sql.upper()
            for keyword in cls.FORBIDDEN_KEYWORDS:
                if re.search(rf'\b{keyword}\b', sql_upper):
                    return False, f"Forbidden keyword: {keyword}"
            
            # Check for forbidden functions
            sql_lower = sql.lower()
            for func in cls.FORBIDDEN_FUNCTIONS:
                if func.lower() in sql_lower:
                    return False, f"Forbidden function: {func}"
            
            # Check for SELECT INTO (data modification)
            if "SELECT" in sql_upper and "INTO" in sql_upper:
                if re.search(r'\bSELECT\b.*\bINTO\b', sql_upper):
                    return False, "SELECT INTO is not allowed"
            
            return True, None
            
        except sqlglot.errors.ParseError as e:
            return False, f"SQL parse error: {str(e)}"
        except Exception as e:
            logger.warning("SQL validation error", error=str(e))
            return False, f"Validation error: {str(e)}"
    
    @classmethod
    def sanitize_identifier(cls, identifier: str) -> str:
        """Sanitize a SQL identifier."""
        return re.sub(r'[^a-zA-Z0-9_]', '', identifier)
    
    @classmethod
    def add_limit_if_missing(cls, sql: str, limit: int = 1000) -> str:
        """Add LIMIT clause if not present."""
        if "LIMIT" not in sql.upper():
            sql = f"{sql.rstrip(';')} LIMIT {limit}"
        return sql


class AnalysisResult(BaseModel):
    """Validated analysis result model."""
    
    analysis: str = Field(..., min_length=10)
    recommendations: str = Field(default="")
    confidence: float = Field(ge=0.0, le=1.0)
    
    @field_validator("confidence", mode="before")
    @classmethod
    def parse_confidence(cls, v: Any) -> float:
        """Parse confidence to float."""
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                return 0.5
        return float(v) if v is not None else 0.5


class QueryResult(BaseModel):
    """Validated query result model."""
    
    success: bool
    data: Optional[list[dict[str, Any]]] = None
    row_count: int = Field(ge=0)
    error: Optional[str] = None
    sql_query: Optional[str] = None


class AgentResponse(BaseModel):
    """Validated agent response model."""
    
    response: str
    analysis: Optional[str] = None
    recommendations: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    data: Optional[list[dict[str, Any]]] = None
    row_count: int = Field(ge=0, default=0)
    session_id: str
    error: Optional[str] = None


class ResultValidator:
    """
    Validates and sanitizes results from the agent.
    """
    
    @staticmethod
    def validate_analysis(
        analysis: str,
        recommendations: str,
        confidence: float,
    ) -> AnalysisResult:
        """
        Validate analysis output.
        
        Args:
            analysis: Analysis text
            recommendations: Recommendations text
            confidence: Confidence score
            
        Returns:
            Validated AnalysisResult
        """
        return AnalysisResult(
            analysis=analysis,
            recommendations=recommendations,
            confidence=confidence,
        )
    
    @staticmethod
    def validate_query_result(
        success: bool,
        data: Optional[list] = None,
        row_count: int = 0,
        error: Optional[str] = None,
        sql_query: Optional[str] = None,
    ) -> QueryResult:
        """
        Validate query result.
        
        Args:
            success: Whether query succeeded
            data: Query result data
            row_count: Number of rows
            error: Error message if any
            sql_query: The SQL query that was executed
            
        Returns:
            Validated QueryResult
        """
        return QueryResult(
            success=success,
            data=data,
            row_count=row_count,
            error=error,
            sql_query=sql_query,
        )
    
    @staticmethod
    def validate_response(
        response: str,
        session_id: str,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Validate full agent response.
        
        Args:
            response: Response text
            session_id: Session identifier
            **kwargs: Additional fields
            
        Returns:
            Validated AgentResponse
        """
        return AgentResponse(
            response=response,
            session_id=session_id,
            **kwargs,
        )
    
    @staticmethod
    def sanitize_results(
        data: list[dict[str, Any]],
        max_rows: int = 1000,
        max_field_length: int = 10000,
    ) -> list[dict[str, Any]]:
        """
        Sanitize query results for safe output.
        
        Args:
            data: Raw query results
            max_rows: Maximum rows to return
            max_field_length: Maximum length per field
            
        Returns:
            Sanitized results
        """
        sanitized = []
        
        for row in data[:max_rows]:
            clean_row = {}
            for key, value in row.items():
                # Truncate long strings
                if isinstance(value, str) and len(value) > max_field_length:
                    value = value[:max_field_length] + "..."
                clean_row[key] = value
            sanitized.append(clean_row)
        
        return sanitized
