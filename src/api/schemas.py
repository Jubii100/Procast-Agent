"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request model for the analyze endpoint."""
    
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language question about budget data",
        examples=["What is the total budget for all projects?"],
    )
    context: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional context for the query",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation continuity",
    )


class AnalyzeResponse(BaseModel):
    """Response model for the analyze endpoint."""
    
    response: str = Field(
        ...,
        description="Human-readable response to the query",
    )
    analysis: Optional[str] = Field(
        default=None,
        description="Detailed analysis text",
    )
    recommendations: Optional[str] = Field(
        default=None,
        description="Actionable recommendations",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0,
        description="Confidence score of the analysis",
    )
    data: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Raw query results (if applicable)",
    )
    row_count: int = Field(
        ge=0,
        default=0,
        description="Number of data rows returned",
    )
    session_id: str = Field(
        ...,
        description="Session ID for this conversation",
    )
    sql_query: Optional[str] = Field(
        default=None,
        description="The SQL query that was executed (if applicable)",
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional metadata about the request",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the request failed",
    )


class SchemaInfo(BaseModel):
    """Database schema information."""
    
    table_name: str
    column_name: str
    data_type: str
    is_nullable: str
    constraint_type: Optional[str] = None


class SchemaResponse(BaseModel):
    """Response model for schema endpoint."""
    
    tables: list[str] = Field(
        ...,
        description="List of table names",
    )
    schema_info: list[SchemaInfo] = Field(
        ...,
        description="Detailed schema information",
    )
    total_tables: int = Field(
        ...,
        description="Total number of tables",
    )


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    
    status: str = Field(
        ...,
        description="Overall health status",
        examples=["healthy", "unhealthy"],
    )
    database: dict[str, Any] = Field(
        ...,
        description="Database health information",
    )
    agent: dict[str, Any] = Field(
        ...,
        description="Agent health information",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of health check",
    )


class SessionInfo(BaseModel):
    """Session information."""
    
    session_id: str
    user_id: str
    created_at: datetime
    last_activity: datetime
    message_count: int


class SessionCreateResponse(BaseModel):
    """Response model for session creation."""
    
    session_id: str
    user_id: str
    created_at: datetime


class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    detail: str = Field(
        ...,
        description="Error message",
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Type of error",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of error",
    )


# =============================================================================
# Session Management Schemas
# =============================================================================


class SessionCreate(BaseModel):
    """Request model for creating a new session."""
    
    title: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Optional session title",
    )


class SessionResponse(BaseModel):
    """Response model for a session."""
    
    id: str = Field(..., description="Session UUID")
    user_id: str = Field(..., description="User identifier")
    email: Optional[str] = Field(default=None, description="User email")
    person_id: Optional[str] = Field(default=None, description="Procast person ID")
    company_id: Optional[str] = Field(default=None, description="Procast company ID")
    title: Optional[str] = Field(default=None, description="Session title")
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_activity: datetime = Field(..., description="Last activity timestamp")
    message_count: int = Field(default=0, description="Number of messages in session")


class SessionListResponse(BaseModel):
    """Response model for listing sessions."""
    
    sessions: list[SessionResponse] = Field(..., description="List of sessions")
    total: int = Field(..., description="Total number of sessions")


class MessageCreate(BaseModel):
    """Request model for adding a message."""
    
    role: str = Field(
        ...,
        pattern="^(user|assistant|system)$",
        description="Message role",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Message content",
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional message metadata",
    )


class MessageResponse(BaseModel):
    """Response model for a message."""
    
    id: int = Field(..., description="Message ID")
    session_id: str = Field(..., description="Session UUID")
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="Message timestamp")
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Message metadata")


class SessionDetailResponse(BaseModel):
    """Response model for session with messages."""
    
    session: SessionResponse = Field(..., description="Session info")
    messages: list[MessageResponse] = Field(..., description="Session messages")


class EventResponse(BaseModel):
    """Response model for an event."""
    
    id: int = Field(..., description="Event ID")
    session_id: str = Field(..., description="Session UUID")
    event_type: str = Field(..., description="Event type")
    payload: Optional[dict[str, Any]] = Field(default=None, description="Event payload")
    timestamp: datetime = Field(..., description="Event timestamp")
