"""Database access for chat sessions and messages."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy import text

from src.db.connection import DatabaseManager
from src.sessions.models import MessageRecord, SessionRecord

logger = structlog.get_logger(__name__)


CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions (updated_at);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages (session_id);",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages (created_at);",
]


async def ensure_chat_tables() -> None:
    """Ensure chat session/message tables exist."""
    async with DatabaseManager.get_admin_session() as session:
        await session.execute(text(CREATE_SESSIONS_TABLE))
        await session.execute(text(CREATE_MESSAGES_TABLE))
        for statement in CREATE_INDEXES:
            await session.execute(text(statement))
        await session.commit()
    logger.info("Chat session tables ensured")


async def create_session(
    user_id: str,
    title: Optional[str] = None,
    session_id: Optional[str] = None,
) -> SessionRecord:
    """Create a new chat session."""
    session_id = session_id or str(uuid4())
    async with DatabaseManager.get_admin_session() as session:
        await session.execute(
            text(
                """
                INSERT INTO chat_sessions (id, user_id, title)
                VALUES (:id, :user_id, :title)
                """
            ),
            {"id": session_id, "user_id": user_id, "title": title},
        )
        await session.commit()

    return SessionRecord(
        id=session_id,
        title=title,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


async def touch_session(session_id: str) -> None:
    """Update session updated_at timestamp."""
    async with DatabaseManager.get_admin_session() as session:
        await session.execute(
            text(
                """
                UPDATE chat_sessions
                SET updated_at = NOW()
                WHERE id = :session_id
                """
            ),
            {"session_id": session_id},
        )
        await session.commit()


async def get_session(
    session_id: str,
    user_id: str,
) -> Optional[SessionRecord]:
    """Get a session owned by user."""
    async with DatabaseManager.get_readonly_session() as session:
        result = await session.execute(
            text(
                """
                SELECT id, title, created_at, updated_at
                FROM chat_sessions
                WHERE id = :session_id AND user_id = :user_id
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        row = result.mappings().first()
        if not row:
            return None

        return SessionRecord(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


async def session_exists(session_id: str) -> bool:
    """Check if a session exists regardless of ownership."""
    async with DatabaseManager.get_readonly_session() as session:
        result = await session.execute(
            text("SELECT 1 FROM chat_sessions WHERE id = :session_id"),
            {"session_id": session_id},
        )
        return result.first() is not None


async def list_sessions(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[SessionRecord]:
    """List sessions for a user."""
    async with DatabaseManager.get_readonly_session() as session:
        result = await session.execute(
            text(
                """
                SELECT id, title, created_at, updated_at
                FROM chat_sessions
                WHERE user_id = :user_id
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"user_id": user_id, "limit": limit, "offset": offset},
        )
        rows = result.mappings().all()

    return [
        SessionRecord(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


async def list_messages(session_id: str) -> list[MessageRecord]:
    """List messages for a session ordered by created_at."""
    async with DatabaseManager.get_readonly_session() as session:
        result = await session.execute(
            text(
                """
                SELECT id, session_id, role, content, created_at
                FROM chat_messages
                WHERE session_id = :session_id
                ORDER BY created_at ASC
                """
            ),
            {"session_id": session_id},
        )
        rows = result.mappings().all()

    return [
        MessageRecord(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


async def insert_message(
    session_id: str,
    role: str,
    content: str,
) -> MessageRecord:
    """Insert a message into a session."""
    message_id = str(uuid4())
    async with DatabaseManager.get_admin_session() as session:
        await session.execute(
            text(
                """
                INSERT INTO chat_messages (id, session_id, role, content)
                VALUES (:id, :session_id, :role, :content)
                """
            ),
            {
                "id": message_id,
                "session_id": session_id,
                "role": role,
                "content": content,
            },
        )
        await session.execute(
            text(
                """
                UPDATE chat_sessions
                SET updated_at = NOW()
                WHERE id = :session_id
                """
            ),
            {"session_id": session_id},
        )
        await session.commit()

    return MessageRecord(
        id=message_id,
        session_id=session_id,
        role=role,
        content=content,
        created_at=datetime.now(timezone.utc),
    )
