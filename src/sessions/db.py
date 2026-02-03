"""SQLite database connection for session storage."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.sessions.models import Base

logger = structlog.get_logger(__name__)

# Default database path (can be overridden by SESSION_DB_PATH env var)
DEFAULT_DB_PATH = Path(os.getenv("SESSION_DB_PATH", "./.data/procast_ai.db"))


class SessionDB:
    """
    Manages the SQLite database connection for session storage.
    
    This is separate from the main Postgres connection used for
    querying the Procast business data.
    """

    _engine: Optional[AsyncEngine] = None
    _session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    _db_path: Optional[Path] = None

    @classmethod
    async def initialize(cls, db_path: Optional[Path] = None) -> None:
        """
        Initialize the SQLite database for sessions.
        
        Args:
            db_path: Path to the SQLite database file. Defaults to ./.data/procast_ai.db
        """
        cls._db_path = db_path or DEFAULT_DB_PATH
        
        # Ensure parent directory exists
        cls._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create async SQLite engine
        db_url = f"sqlite+aiosqlite:///{cls._db_path}"
        
        cls._engine = create_async_engine(
            db_url,
            echo=False,  # Set to True for debugging
            future=True,
        )
        
        cls._session_factory = async_sessionmaker(
            cls._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        
        # Create tables if they don't exist
        async with cls._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Session database initialized", db_path=str(cls._db_path))

    @classmethod
    async def close(cls) -> None:
        """Close the database connection."""
        if cls._engine:
            await cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None
            logger.info("Session database closed")

    @classmethod
    @asynccontextmanager
    async def get_session(cls) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session.
        
        Yields:
            AsyncSession for database operations
        """
        if cls._session_factory is None:
            raise RuntimeError(
                "Session database not initialized. Call SessionDB.initialize() first."
            )

        session = cls._session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Session database error", error=str(e))
            raise
        finally:
            await session.close()

    @classmethod
    def get_db_path(cls) -> Optional[Path]:
        """Get the current database path."""
        return cls._db_path

    @classmethod
    async def health_check(cls) -> dict:
        """
        Check session database health.
        
        Returns:
            Health status dictionary
        """
        result = {
            "status": "unknown",
            "db_path": str(cls._db_path) if cls._db_path else None,
            "connected": False,
            "error": None,
        }

        try:
            if cls._session_factory is None:
                result["status"] = "not_initialized"
                return result

            async with cls.get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
                result["connected"] = True
                result["status"] = "healthy"

        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            logger.error("Session database health check failed", error=str(e))

        return result
