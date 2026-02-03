"""Session management endpoints for the Procast AI agent."""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect

from src.api.middleware.auth import get_current_user, UserContext
from src.api.schemas import (
    SessionCreate,
    SessionResponse,
    SessionListResponse,
    SessionDetailResponse,
    MessageCreate,
    MessageResponse,
    EventResponse,
    ErrorResponse,
)
from src.sessions.repo import SessionRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


def _session_to_response(session) -> SessionResponse:
    """Convert a Session model to SessionResponse."""
    # Avoid lazy-loading on detached instances
    state = inspect(session)
    if "messages" in state.unloaded:
        message_count = 0
    else:
        message_count = len(session.messages) if session.messages else 0

    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        email=session.email,
        person_id=session.person_id,
        company_id=session.company_id,
        title=session.title,
        created_at=session.created_at,
        last_activity=session.last_activity,
        message_count=message_count,
    )


def _message_to_response(message) -> MessageResponse:
    """Convert a Message model to MessageResponse."""
    return MessageResponse(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        timestamp=message.timestamp,
        metadata=message.message_metadata,
    )


def _event_to_response(event) -> EventResponse:
    """Convert an Event model to EventResponse."""
    return EventResponse(
        id=event.id,
        session_id=event.session_id,
        event_type=event.event_type,
        payload=event.payload,
        timestamp=event.timestamp,
    )


@router.post(
    "",
    response_model=SessionResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Create a new session",
    description="Create a new conversation session for tracking chat history.",
)
async def create_session(
    request: Optional[SessionCreate] = None,
    user: UserContext = Depends(get_current_user),
) -> SessionResponse:
    """Create a new conversation session."""
    logger.info(
        "Creating session",
        user_id=user.user_id,
        email=user.email,
    )
    
    try:
        session = await SessionRepository.create_session(
            user_id=user.user_id,
            email=user.email,
            person_id=user.person_id,
            company_id=user.company_id,
            title=request.title if request else None,
        )
        
        return _session_to_response(session)
        
    except Exception as e:
        logger.error("Failed to create session", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.get(
    "",
    response_model=SessionListResponse,
    summary="List sessions",
    description="List all sessions for the current user.",
)
async def list_sessions(
    user: UserContext = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum sessions to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> SessionListResponse:
    """List sessions for the current user."""
    try:
        sessions = await SessionRepository.list_sessions(
            user_id=user.user_id,
            limit=limit,
            offset=offset,
        )
        
        return SessionListResponse(
            sessions=[_session_to_response(s) for s in sessions],
            total=len(sessions),  # TODO: Add actual count query
        )
        
    except Exception as e:
        logger.error("Failed to list sessions", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Get session details",
    description="Get a session with all its messages.",
)
async def get_session(
    session_id: str,
    user: UserContext = Depends(get_current_user),
) -> SessionDetailResponse:
    """Get a session with its messages."""
    try:
        session = await SessionRepository.get_session_with_messages(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Verify ownership
        if session.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return SessionDetailResponse(
            session=_session_to_response(session),
            messages=[_message_to_response(m) for m in session.messages],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get session", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Add a message",
    description="Add a message to a session.",
)
async def add_message(
    session_id: str,
    request: MessageCreate,
    user: UserContext = Depends(get_current_user),
) -> MessageResponse:
    """Add a message to a session."""
    try:
        # Verify session exists and belongs to user
        session = await SessionRepository.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        
        message = await SessionRepository.add_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            metadata=request.metadata,
        )
        
        return _message_to_response(message)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to add message", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to add message: {str(e)}")


@router.get(
    "/{session_id}/messages",
    response_model=list[MessageResponse],
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Get messages",
    description="Get all messages in a session.",
)
async def get_messages(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    limit: Optional[int] = Query(default=None, ge=1, le=500, description="Maximum messages to return"),
) -> list[MessageResponse]:
    """Get messages for a session."""
    try:
        # Verify session exists and belongs to user
        session = await SessionRepository.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        
        messages = await SessionRepository.get_messages(session_id, limit=limit)
        
        return [_message_to_response(m) for m in messages]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get messages", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")


@router.get(
    "/{session_id}/events",
    response_model=list[EventResponse],
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Get events",
    description="Get logged events for a session.",
)
async def get_events(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    limit: Optional[int] = Query(default=None, ge=1, le=500, description="Maximum events to return"),
) -> list[EventResponse]:
    """Get events for a session."""
    try:
        # Verify session exists and belongs to user
        session = await SessionRepository.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        
        events = await SessionRepository.get_events(
            session_id, 
            event_type=event_type,
            limit=limit,
        )
        
        return [_event_to_response(e) for e in events]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get events", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get events: {str(e)}")


@router.patch(
    "/{session_id}",
    response_model=SessionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
    },
    summary="Update session",
    description="Update session title.",
)
async def update_session(
    session_id: str,
    request: SessionCreate,
    user: UserContext = Depends(get_current_user),
) -> SessionResponse:
    """Update a session."""
    try:
        session = await SessionRepository.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if request.title:
            await SessionRepository.update_session_title(session_id, request.title)
        
        # Fetch updated session
        session = await SessionRepository.get_session(session_id)
        return _session_to_response(session)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update session", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update session: {str(e)}")
