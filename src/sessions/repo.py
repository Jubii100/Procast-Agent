"""Repository for session data access."""

from datetime import datetime
from typing import Any, Optional
import uuid

import structlog
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.sessions.models import Session, Message, Event
from src.sessions.db import SessionDB

logger = structlog.get_logger(__name__)


class SessionRepository:
    """
    Repository for session CRUD operations.
    
    Provides methods for creating, reading, and updating sessions,
    messages, and events.
    """

    # =========================================================================
    # Session Operations
    # =========================================================================

    @classmethod
    async def create_session(
        cls,
        user_id: str,
        email: Optional[str] = None,
        person_id: Optional[str] = None,
        company_id: Optional[str] = None,
        title: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """
        Create a new session.
        
        Args:
            user_id: User identifier
            email: User's email
            person_id: Procast person ID
            company_id: Procast company ID
            title: Optional session title
            session_id: Optional pre-generated session ID
            
        Returns:
            Created Session object
        """
        session_id = session_id or str(uuid.uuid4())
        
        async with SessionDB.get_session() as db:
            session = Session(
                id=session_id,
                user_id=user_id,
                email=email,
                person_id=person_id,
                company_id=company_id,
                title=title,
                created_at=datetime.utcnow(),
                last_activity=datetime.utcnow(),
            )
            db.add(session)
            await db.flush()
            
            logger.info(
                "Session created",
                session_id=session_id,
                user_id=user_id,
            )
            
            return session

    @classmethod
    async def get_session(cls, session_id: str) -> Optional[Session]:
        """
        Get a session by ID.
        
        Args:
            session_id: Session UUID
            
        Returns:
            Session object or None
        """
        async with SessionDB.get_session() as db:
            result = await db.execute(
                select(Session)
                .options(selectinload(Session.messages))
                .where(Session.id == session_id)
            )
            return result.scalar_one_or_none()

    @classmethod
    async def get_session_with_messages(cls, session_id: str) -> Optional[Session]:
        """
        Get a session with all messages loaded.
        
        Args:
            session_id: Session UUID
            
        Returns:
            Session object with messages or None
        """
        async with SessionDB.get_session() as db:
            result = await db.execute(
                select(Session)
                .options(
                    selectinload(Session.messages),
                    selectinload(Session.events),
                )
                .where(Session.id == session_id)
            )
            return result.scalar_one_or_none()

    @classmethod
    async def list_sessions(
        cls,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Session]:
        """
        List sessions for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            offset: Offset for pagination
            
        Returns:
            List of Session objects
        """
        async with SessionDB.get_session() as db:
            result = await db.execute(
                select(Session)
                .where(Session.user_id == user_id)
                .order_by(desc(Session.last_activity))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    @classmethod
    async def update_session_activity(cls, session_id: str) -> None:
        """
        Update the last_activity timestamp for a session.
        
        Args:
            session_id: Session UUID
        """
        async with SessionDB.get_session() as db:
            await db.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(last_activity=datetime.utcnow())
            )

    @classmethod
    async def update_session_title(cls, session_id: str, title: str) -> None:
        """
        Update the title for a session.
        
        Args:
            session_id: Session UUID
            title: New title
        """
        async with SessionDB.get_session() as db:
            await db.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(title=title)
            )

    @classmethod
    async def get_or_create_session(
        cls,
        session_id: Optional[str],
        user_id: str,
        email: Optional[str] = None,
        person_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> tuple[Session, bool]:
        """
        Get an existing session or create a new one.
        
        Args:
            session_id: Optional session ID to look up
            user_id: User identifier
            email: User's email
            person_id: Procast person ID
            company_id: Procast company ID
            
        Returns:
            Tuple of (Session, was_created)
        """
        if session_id:
            session = await cls.get_session(session_id)
            if session:
                await cls.update_session_activity(session_id)
                return session, False
        
        # Create new session
        session = await cls.create_session(
            user_id=user_id,
            email=email,
            person_id=person_id,
            company_id=company_id,
            session_id=session_id,
        )
        return session, True

    # =========================================================================
    # Message Operations
    # =========================================================================

    @classmethod
    async def add_message(
        cls,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Message:
        """
        Add a message to a session.
        
        Args:
            session_id: Session UUID
            role: Message role ("user", "assistant", "system")
            content: Message content
            metadata: Optional message metadata
            
        Returns:
            Created Message object
        """
        async with SessionDB.get_session() as db:
            message = Message(
                session_id=session_id,
                role=role,
                content=content,
                timestamp=datetime.utcnow(),
            )
            message.message_metadata = metadata
            db.add(message)
            await db.flush()
            
            # Update session activity
            await db.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(last_activity=datetime.utcnow())
            )
            
            logger.debug(
                "Message added",
                session_id=session_id,
                role=role,
                content_length=len(content),
            )
            
            return message

    @classmethod
    async def get_messages(
        cls,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[Message]:
        """
        Get messages for a session.
        
        Args:
            session_id: Session UUID
            limit: Optional limit on number of messages
            
        Returns:
            List of Message objects
        """
        async with SessionDB.get_session() as db:
            query = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.timestamp)
            )
            if limit:
                query = query.limit(limit)
            
            result = await db.execute(query)
            return list(result.scalars().all())

    # =========================================================================
    # Event Operations
    # =========================================================================

    @classmethod
    async def log_event(
        cls,
        session_id: str,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Event:
        """
        Log an event for a session.
        
        Args:
            session_id: Session UUID
            event_type: Type of event (e.g., "sql_generated", "query_executed")
            payload: Event data
            
        Returns:
            Created Event object
        """
        async with SessionDB.get_session() as db:
            event = Event(
                session_id=session_id,
                event_type=event_type,
                timestamp=datetime.utcnow(),
            )
            event.payload = payload
            db.add(event)
            await db.flush()
            
            logger.debug(
                "Event logged",
                session_id=session_id,
                event_type=event_type,
            )
            
            return event

    @classmethod
    async def get_events(
        cls,
        session_id: str,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[Event]:
        """
        Get events for a session.
        
        Args:
            session_id: Session UUID
            event_type: Optional filter by event type
            limit: Optional limit on number of events
            
        Returns:
            List of Event objects
        """
        async with SessionDB.get_session() as db:
            query = (
                select(Event)
                .where(Event.session_id == session_id)
            )
            if event_type:
                query = query.where(Event.event_type == event_type)
            query = query.order_by(Event.timestamp)
            if limit:
                query = query.limit(limit)
            
            result = await db.execute(query)
            return list(result.scalars().all())

    # =========================================================================
    # Conversation History for Agent
    # =========================================================================

    @classmethod
    async def get_conversation_history(
        cls,
        session_id: str,
        max_messages: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Get conversation history in agent-compatible format.
        
        Args:
            session_id: Session UUID
            max_messages: Maximum number of messages to include
            
        Returns:
            List of message dictionaries for agent state
        """
        messages = await cls.get_messages(session_id, limit=max_messages)
        
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "metadata": msg.message_metadata,
            }
            for msg in messages
        ]
