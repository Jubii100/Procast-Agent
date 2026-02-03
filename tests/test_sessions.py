"""Tests for session storage and management."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.sessions.models import Session, Message, Event
from src.sessions.repo import SessionRepository


class TestSessionModels:
    """Tests for session SQLAlchemy models."""

    def test_session_to_dict(self):
        """Test Session.to_dict() method."""
        session = Session(
            id="test-session-123",
            user_id="user-456",
            email="test@example.com",
            person_id="person-789",
            company_id="company-abc",
            title="Test Session",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            last_activity=datetime(2024, 1, 1, 12, 30, 0),
        )
        session.messages = []
        
        result = session.to_dict()
        
        assert result["id"] == "test-session-123"
        assert result["user_id"] == "user-456"
        assert result["email"] == "test@example.com"
        assert result["person_id"] == "person-789"
        assert result["title"] == "Test Session"
        assert result["message_count"] == 0

    def test_message_to_dict(self):
        """Test Message.to_dict() method."""
        message = Message(
            id=1,
            session_id="test-session-123",
            role="user",
            content="Hello, world!",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )
        message.metadata = {"key": "value"}
        
        result = message.to_dict()
        
        assert result["id"] == 1
        assert result["session_id"] == "test-session-123"
        assert result["role"] == "user"
        assert result["content"] == "Hello, world!"
        assert result["metadata"] == {"key": "value"}

    def test_message_metadata_property(self):
        """Test Message metadata property serialization."""
        message = Message(
            id=1,
            session_id="test-session-123",
            role="assistant",
            content="Response",
        )
        
        # Test setting metadata
        message.metadata = {"confidence": 0.95, "tokens": 100}
        assert message._metadata is not None
        
        # Test getting metadata
        retrieved = message.metadata
        assert retrieved["confidence"] == 0.95
        assert retrieved["tokens"] == 100
        
        # Test None metadata
        message.metadata = None
        assert message._metadata is None
        assert message.metadata is None

    def test_event_to_dict(self):
        """Test Event.to_dict() method."""
        event = Event(
            id=1,
            session_id="test-session-123",
            event_type="sql_generated",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )
        event.payload = {"sql": "SELECT * FROM projects"}
        
        result = event.to_dict()
        
        assert result["id"] == 1
        assert result["session_id"] == "test-session-123"
        assert result["event_type"] == "sql_generated"
        assert result["payload"]["sql"] == "SELECT * FROM projects"

    def test_event_payload_property(self):
        """Test Event payload property serialization."""
        event = Event(
            id=1,
            session_id="test-session-123",
            event_type="query_completed",
        )
        
        # Test setting payload with various types
        event.payload = {
            "confidence": 0.85,
            "timestamp": datetime(2024, 1, 1),  # Should be serialized
        }
        assert event._payload is not None
        
        # Test getting payload
        retrieved = event.payload
        assert retrieved["confidence"] == 0.85


class TestSessionSchemas:
    """Tests for session API schemas."""

    def test_session_response_schema(self):
        """Test SessionResponse schema."""
        from src.api.schemas import SessionResponse
        
        response = SessionResponse(
            id="test-session-123",
            user_id="user-456",
            email="test@example.com",
            person_id="person-789",
            company_id="company-abc",
            title="Test Session",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            last_activity=datetime(2024, 1, 1, 12, 30, 0),
            message_count=5,
        )
        
        assert response.id == "test-session-123"
        assert response.message_count == 5

    def test_message_create_schema_validation(self):
        """Test MessageCreate schema validation."""
        from src.api.schemas import MessageCreate
        
        # Valid message
        msg = MessageCreate(role="user", content="Hello")
        assert msg.role == "user"
        
        # Invalid role should raise validation error
        with pytest.raises(ValueError):
            MessageCreate(role="invalid", content="Hello")

    def test_session_create_schema(self):
        """Test SessionCreate schema."""
        from src.api.schemas import SessionCreate
        
        # Without title
        create = SessionCreate()
        assert create.title is None
        
        # With title
        create = SessionCreate(title="My Session")
        assert create.title == "My Session"


class TestSessionDB:
    """Tests for SessionDB connection management."""

    @pytest.mark.asyncio
    async def test_session_db_health_check_not_initialized(self):
        """Test health check when DB is not initialized."""
        from src.sessions.db import SessionDB
        
        # Ensure not initialized
        SessionDB._session_factory = None
        SessionDB._engine = None
        
        result = await SessionDB.health_check()
        
        assert result["status"] == "not_initialized"
        assert result["connected"] is False


class TestSessionRepository:
    """Tests for SessionRepository (mocked)."""

    @pytest.mark.asyncio
    async def test_create_session_generates_uuid(self):
        """Test that create_session generates a UUID if not provided."""
        with patch('src.sessions.repo.SessionDB') as mock_db:
            mock_session = AsyncMock()
            mock_db.get_session.return_value.__aenter__.return_value = mock_session
            
            # Mock the session behavior
            async def mock_flush():
                pass
            mock_session.flush = mock_flush
            mock_session.add = MagicMock()
            
            session = await SessionRepository.create_session(
                user_id="test-user",
                email="test@example.com",
            )
            
            assert session.id is not None
            assert len(session.id) == 36  # UUID format
            assert session.user_id == "test-user"
            assert session.email == "test@example.com"


class TestAnalyzeIntegration:
    """Integration tests for analyze endpoint with sessions."""

    def test_analyze_response_includes_session_id(self):
        """Test that analyze response includes session_id."""
        from src.api.schemas import AnalyzeResponse
        
        response = AnalyzeResponse(
            response="Test response",
            session_id="test-session-123",
            confidence=0.85,
        )
        
        assert response.session_id == "test-session-123"
        assert response.confidence == 0.85
