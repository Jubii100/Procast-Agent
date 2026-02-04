"""Session endpoints for chat UI."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.middleware.auth import get_current_user, UserContext
from src.api.schemas import MessageResponse, SessionDetailResponse, SessionResponse
from src.sessions.db import get_session, list_messages, list_sessions, session_exists

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Sessions"])


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    summary="List sessions",
    description="Return sessions for the authenticated user.",
)
async def list_user_sessions(
    user: UserContext = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SessionResponse]:
    try:
        sessions = await list_sessions(user.user_id, limit=limit, offset=offset)
    except Exception as e:
        logger.error("Failed to list sessions", error=str(e), user_id=user.user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sessions",
        )

    return [
        SessionResponse(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        for session in sessions
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session detail",
    description="Return a single session with ordered message history.",
)
async def get_session_detail(
    session_id: str,
    user: UserContext = Depends(get_current_user),
) -> SessionDetailResponse:
    try:
        session = await get_session(session_id, user.user_id)
        if session is None:
            if await session_exists(session_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access to session denied",
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )

        messages = await list_messages(session_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to fetch session detail",
            error=str(e),
            user_id=user.user_id,
            session_id=session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch session detail",
        )

    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            MessageResponse(
                id=message.id,
                session_id=message.session_id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )
