"""Data models for chat sessions and messages."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class SessionRecord:
    """Session record from storage."""

    id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageRecord:
    """Message record from storage."""

    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
