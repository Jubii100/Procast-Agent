"""Pydantic schemas for API request/response models."""

from datetime import datetime
from typing import Any, Optional, Literal

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


# ---------------------------------------------------------------------------
# UI Message Stream Protocol Types (Vercel AI SDK 5+)
# ---------------------------------------------------------------------------


class TextPart(BaseModel):
    """Text part within a message."""

    type: Literal["text"] = "text"
    text: str


class ToolCallPart(BaseModel):
    """Tool call part within a message."""

    type: Literal["tool-call"] = "tool-call"
    toolCallId: str
    toolName: str
    args: dict[str, Any]


class ToolResultPart(BaseModel):
    """Tool result part within a message."""

    type: Literal["tool-result"] = "tool-result"
    toolCallId: str
    result: Any


MessagePart = TextPart | ToolCallPart | ToolResultPart


class ChatMessage(BaseModel):
    """Chat message supporting both legacy and UI Message Stream formats."""

    role: Literal["user", "assistant", "system"]
    # Legacy format (backwards compatibility)
    content: Optional[str] = None
    # New format (UI Message Stream Protocol)
    parts: Optional[list[MessagePart]] = None

    def get_text_content(self) -> str:
        """Extract text content from message, supporting both formats."""
        # New format: parts array
        if self.parts:
            text_parts = [
                part.text for part in self.parts if isinstance(part, TextPart)
            ]
            return "".join(text_parts)
        # Legacy format: content string
        if self.content:
            return self.content
        return ""

    def get_tool_calls(self) -> list[ToolCallPart]:
        """Extract tool calls from message parts."""
        if not self.parts:
            return []
        return [part for part in self.parts if isinstance(part, ToolCallPart)]


class ChatStreamRequest(BaseModel):
    """Request payload for streaming chat."""

    session_id: str = Field(..., description="Session ID for persistence")
    messages: list[ChatMessage] = Field(
        ...,
        description="Conversation messages (supports legacy content or parts array)",
    )
    model: Optional[str] = Field(
        default=None,
        description="Optional model override",
    )
    temperature: Optional[float] = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Sampling temperature",
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


class SessionResponse(BaseModel):
    """Session response for list endpoints."""

    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """Message response for session detail."""

    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class SessionDetailResponse(SessionResponse):
    """Session detail response with message history."""

    messages: list[MessageResponse]


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
