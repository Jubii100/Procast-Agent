"""SQLAlchemy models for session storage."""

from datetime import datetime
from typing import Any, Optional
import json

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    Integer,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all session models."""
    pass


class Session(Base):
    """
    Session model for tracking conversation sessions.
    
    Links to user identity and contains metadata about the session.
    """
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(256), nullable=False, index=True)
    email = Column(String(256), nullable=True, index=True)
    person_id = Column(String(36), nullable=True, index=True)
    company_id = Column(String(36), nullable=True)
    title = Column(String(512), nullable=True)  # Optional session title
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan", order_by="Message.timestamp")
    events = relationship("Event", back_populates="session", cascade="all, delete-orphan", order_by="Event.timestamp")

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.email,
            "person_id": self.person_id,
            "company_id": self.company_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "message_count": len(self.messages) if self.messages else 0,
        }


class Message(Base):
    """
    Message model for storing conversation messages.
    
    Each message belongs to a session and has a role (user/assistant/system).
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    _metadata = Column("metadata", Text, nullable=True)  # JSON string

    # Relationships
    session = relationship("Session", back_populates="messages")

    @property
    def message_metadata(self) -> Optional[dict[str, Any]]:
        """Parse metadata JSON."""
        if self._metadata:
            try:
                return json.loads(self._metadata)
            except json.JSONDecodeError:
                return None
        return None

    @message_metadata.setter
    def message_metadata(self, value: Optional[dict[str, Any]]) -> None:
        """Serialize metadata to JSON."""
        if value is not None:
            self._metadata = json.dumps(value)
        else:
            self._metadata = None

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.message_metadata,
        }


class Event(Base):
    """
    Event model for logging agent behavior and metrics.
    
    Stores events like SQL generation, query execution, LLM calls, etc.
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # "sql_generated", "query_executed", "llm_call", etc.
    _payload = Column("payload", Text, nullable=True)  # JSON string
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("Session", back_populates="events")

    @property
    def payload(self) -> Optional[dict[str, Any]]:
        """Parse payload JSON."""
        if self._payload:
            try:
                return json.loads(self._payload)
            except json.JSONDecodeError:
                return None
        return None

    @payload.setter
    def payload(self, value: Optional[dict[str, Any]]) -> None:
        """Serialize payload to JSON."""
        if value is not None:
            self._payload = json.dumps(value, default=str)
        else:
            self._payload = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
