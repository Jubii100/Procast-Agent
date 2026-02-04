"""Chat streaming endpoint for Next.js UI.

Implements Vercel AI SDK 5+ UI Message Stream Protocol using NDJSON format.
"""

import json
import uuid
from typing import AsyncGenerator, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from src.agent.graph import get_agent
from src.api.middleware.auth import get_current_user, UserContext
from src.api.schemas import ChatStreamRequest, ChatMessage
from src.sessions.db import (
    create_session,
    get_session,
    insert_message,
    session_exists,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Chat"])


# ---------------------------------------------------------------------------
# NDJSON Event Helpers (UI Message Stream Protocol - Vercel AI SDK v5+)
# ---------------------------------------------------------------------------


def _ndjson_event(data: dict[str, Any]) -> str:
    """Format a single NDJSON line (no 'data:' prefix, single newline)."""
    return json.dumps(data) + "\n"


def _event_start() -> str:
    """Stream lifecycle: start event."""
    return _ndjson_event({"type": "start"})


def _event_finish() -> str:
    """Stream lifecycle: finish event."""
    return _ndjson_event({"type": "finish"})


def _event_text_start(text_id: str) -> str:
    """Begin a text part."""
    return _ndjson_event({"type": "text-start", "id": text_id})


def _event_text_delta(text_id: str, delta: str) -> str:
    """Send incremental text chunk."""
    return _ndjson_event({"type": "text-delta", "id": text_id, "delta": delta})


def _event_text_end(text_id: str) -> str:
    """End a text part."""
    return _ndjson_event({"type": "text-end", "id": text_id})


def _event_tool_input_start(tool_call_id: str, tool_name: str) -> str:
    """Tool call initiated."""
    return _ndjson_event({
        "type": "tool-input-start",
        "toolCallId": tool_call_id,
        "toolName": tool_name,
    })


def _event_tool_input_available(
    tool_call_id: str, tool_name: str, input_args: dict[str, Any]
) -> str:
    """Tool arguments ready."""
    return _ndjson_event({
        "type": "tool-input-available",
        "toolCallId": tool_call_id,
        "toolName": tool_name,
        "input": input_args,
    })


def _event_tool_output_available(tool_call_id: str, output: Any) -> str:
    """Tool result ready."""
    return _ndjson_event({
        "type": "tool-output-available",
        "toolCallId": tool_call_id,
        "output": output,
    })


def _event_tool_output_error(tool_call_id: str, error_text: str) -> str:
    """Tool execution failed."""
    return _ndjson_event({
        "type": "tool-output-error",
        "toolCallId": tool_call_id,
        "errorText": error_text,
    })


def _event_error(error_text: str) -> str:
    """Stream-level error."""
    return _ndjson_event({"type": "error", "errorText": error_text})


def _generate_id(prefix: str = "text") -> str:
    """Generate unique ID for stream events."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _chunk_text(text: str, chunk_size: int = 50) -> list[str]:
    """Split text into chunks for streaming."""
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _extract_user_message(messages: list[ChatMessage]) -> str | None:
    """Extract the latest user message content from the messages list."""
    for message in reversed(messages):
        if message.role == "user":
            return message.get_text_content()
    return None


async def _stream_agent_response(
    user_message: str,
    user_id: str,
    session_id: str,
) -> AsyncGenerator[str, None]:
    """
    Run the agent and stream events in real-time using UI Message Stream Protocol.

    Streams events AS the agent executes nodes, providing real-time feedback:
    - start/finish for lifecycle
    - tool events as agent nodes execute (classify, select_tables, generate_sql, etc.)
    - text-start/text-delta/text-end for response text
    """
    yield _event_start()

    agent = await get_agent()
    
    # Track tool calls by node name
    node_tool_ids: dict[str, str] = {}
    final_result: dict[str, Any] | None = None
    
    try:
        async for event in agent.stream_query(
            question=user_message,
            user_id=user_id,
            session_id=session_id,
        ):
            event_type = event.get("event")
            
            if event_type == "node_start":
                # Emit tool-input-start for each node
                node_name = event.get("node", "unknown")
                tool_id = _generate_id("call")
                node_tool_ids[node_name] = tool_id
                yield _event_tool_input_start(tool_id, node_name)
            
            elif event_type == "node_end":
                # Emit tool-input-available and tool-output-available
                node_name = event.get("node", "unknown")
                tool_id = node_tool_ids.get(node_name, _generate_id("call"))
                node_data = event.get("data", {})
                
                # Build input/output based on node type
                if node_name == "classify_intent":
                    yield _event_tool_input_available(tool_id, node_name, {"question": user_message})
                    yield _event_tool_output_available(tool_id, {"intent": node_data.get("intent")})
                
                elif node_name == "select_tables":
                    yield _event_tool_input_available(tool_id, node_name, {"intent": "select relevant tables"})
                    yield _event_tool_output_available(tool_id, {"selected_domains": node_data.get("selected_domains")})
                
                elif node_name == "generate_sql":
                    sql = node_data.get("generated_sql", "")
                    yield _event_tool_input_available(tool_id, node_name, {"task": "generate SQL query"})
                    yield _event_tool_output_available(tool_id, {"sql": sql[:200] + "..." if len(sql) > 200 else sql})
                
                elif node_name == "validate_sql":
                    yield _event_tool_input_available(tool_id, node_name, {"sql": "validating..."})
                    yield _event_tool_output_available(tool_id, {"valid": node_data.get("sql_valid", False)})
                
                elif node_name == "execute_query":
                    row_count = node_data.get("query_row_count", 0)
                    yield _event_tool_input_available(tool_id, node_name, {"action": "execute SQL"})
                    yield _event_tool_output_available(tool_id, {"row_count": row_count})
                
                elif node_name == "analyze_results":
                    yield _event_tool_input_available(tool_id, node_name, {"action": "analyze query results"})
                    yield _event_tool_output_available(tool_id, {"status": "analysis complete"})
                
                elif node_name == "format_response":
                    yield _event_tool_input_available(tool_id, node_name, {"action": "format final response"})
                    yield _event_tool_output_available(tool_id, {"status": "formatting complete"})
                
                elif node_name in ("handle_clarification", "handle_general_info", "handle_error"):
                    yield _event_tool_input_available(tool_id, node_name, {"action": node_name})
                    yield _event_tool_output_available(tool_id, {"status": "complete"})
                
                else:
                    # Generic handling for unknown nodes
                    yield _event_tool_input_available(tool_id, node_name, {})
                    yield _event_tool_output_available(tool_id, node_data)
            
            elif event_type == "complete":
                final_result = event.get("result", {})
            
            elif event_type == "error":
                yield _event_error(event.get("error", "Unknown error"))
                yield _event_finish()
                return

    except Exception as e:
        logger.error(
            "Agent streaming failed",
            error=str(e),
            user_id=user_id,
            session_id=session_id,
        )
        yield _event_error(str(e))
        yield _event_finish()
        return

    # Stream the final response text
    if final_result:
        assistant_message = final_result.get("response", "")
        if assistant_message:
            text_id = _generate_id("text")
            yield _event_text_start(text_id)

            # Stream in chunks for real-time effect
            for chunk in _chunk_text(assistant_message, chunk_size=50):
                yield _event_text_delta(text_id, chunk)

            yield _event_text_end(text_id)

    yield _event_finish()


@router.post(
    "/chat/stream",
    summary="Stream chat response",
    description="Stream assistant response using Vercel AI SDK 5+ UI Message Stream Protocol (NDJSON).",
)
async def stream_chat(
    request: ChatStreamRequest,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    """
    Streaming chat endpoint compatible with Vercel AI SDK useChat.

    Supports both legacy (content) and new (parts) message formats.
    Returns NDJSON stream with UI Message Stream Protocol events.
    """
    # Ensure session exists and user owns it
    try:
        session = await get_session(request.session_id, user.user_id)
        if session is None:
            if await session_exists(request.session_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access to session denied",
                )
            await create_session(user_id=user.user_id, session_id=request.session_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to validate session",
            error=str(e),
            user_id=user.user_id,
            session_id=request.session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate session",
        )

    # Extract latest user message (supports both content and parts formats)
    user_message = _extract_user_message(request.messages)

    if not user_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one user message is required",
        )

    # Persist user message
    try:
        await insert_message(request.session_id, "user", user_message)
    except Exception as e:
        logger.error(
            "Failed to persist user message",
            error=str(e),
            user_id=user.user_id,
            session_id=request.session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store user message",
        )

    # Create the streaming response generator
    async def response_generator() -> AsyncGenerator[str, None]:
        assistant_message_parts: list[str] = []

        async for event in _stream_agent_response(
            user_message=user_message,
            user_id=user.user_id,
            session_id=request.session_id,
        ):
            yield event
            # Capture text deltas to persist the final message
            try:
                data = json.loads(event.strip())
                if data.get("type") == "text-delta":
                    assistant_message_parts.append(data.get("delta", ""))
            except (json.JSONDecodeError, AttributeError):
                pass

        # Persist the complete assistant message after streaming
        if assistant_message_parts:
            full_message = "".join(assistant_message_parts)
            try:
                await insert_message(request.session_id, "assistant", full_message)
            except Exception as e:
                logger.error(
                    "Failed to persist assistant message",
                    error=str(e),
                    user_id=user.user_id,
                    session_id=request.session_id,
                )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Disable nginx proxy buffering
    }
    # #region agent log
    import os; open("/home/mohammed/Desktop/tech_projects/procast-ai/.cursor/debug.log", "a").write(json.dumps({"hypothesisId": "D", "location": "chat.py:stream_chat:response", "message": "StreamingResponse created", "data": {"media_type": "text/plain; charset=utf-8", "headers": headers}, "timestamp": __import__("time").time(), "sessionId": "debug-session"}) + "\n")
    # #endregion
    return StreamingResponse(
        response_generator(),
        media_type="text/plain; charset=utf-8",  # NDJSON format for AI SDK v5+
        headers=headers,
    )
