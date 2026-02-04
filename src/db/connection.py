"""Database connection management using SQLAlchemy async."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings

logger = structlog.get_logger(__name__)


def _convert_to_async_url(url: str) -> str:
    """Convert a standard PostgreSQL URL to asyncpg format."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class DatabaseManager:
    """
    Manages database connections with connection pooling.
    
    Provides both read-only and admin connections for different use cases.
    The AI agent should always use read-only connections.
    """

    _readonly_engine: Optional[AsyncEngine] = None
    _admin_engine: Optional[AsyncEngine] = None
    _readonly_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    _admin_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    @classmethod
    async def initialize(cls, use_readonly: bool = True) -> None:
        """
        Initialize database engines and session factories.
        
        Args:
            use_readonly: If True, initializes only the read-only connection for AI agent.
        """
        logger.info("Initializing database connections")

        # Always create the read-only engine for AI operations
        readonly_url = _convert_to_async_url(str(settings.database_url_readonly))
        cls._readonly_engine = create_async_engine(
            readonly_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
            echo=settings.api_debug,
        )
        cls._readonly_session_factory = async_sessionmaker(
            cls._readonly_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # Optionally create admin engine (for setup scripts and write operations)
        if not use_readonly:
            admin_url = _convert_to_async_url(str(settings.database_url))
            cls._admin_engine = create_async_engine(
                admin_url,
                pool_size=2,  # Minimal pool for admin operations
                max_overflow=2,
                pool_timeout=30,
                pool_pre_ping=True,
                echo=settings.api_debug,
            )
            cls._admin_session_factory = async_sessionmaker(
                cls._admin_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

        logger.info("Database connections initialized")

    @classmethod
    async def close(cls) -> None:
        """Close all database connections."""
        logger.info("Closing database connections")
        
        if cls._readonly_engine:
            await cls._readonly_engine.dispose()
            cls._readonly_engine = None
            cls._readonly_session_factory = None

        if cls._admin_engine:
            await cls._admin_engine.dispose()
            cls._admin_engine = None
            cls._admin_session_factory = None

        logger.info("Database connections closed")

    @classmethod
    def get_readonly_engine(cls) -> AsyncEngine:
        """Get the read-only async engine."""
        if cls._readonly_engine is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.initialize() first."
            )
        return cls._readonly_engine

    @classmethod
    def get_admin_engine(cls) -> AsyncEngine:
        """Get the admin async engine for write operations."""
        if cls._admin_engine is None:
            raise RuntimeError(
                "Admin database not initialized. Call DatabaseManager.initialize(use_readonly=False) first."
            )
        return cls._admin_engine

    @classmethod
    @asynccontextmanager
    async def get_readonly_session(cls) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a read-only database session.
        
        This is the primary method for AI agent database access.
        All queries are guaranteed to be read-only at the database level.
        """
        if cls._readonly_session_factory is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.initialize() first."
            )

        session = cls._readonly_session_factory()
        try:
            yield session
        except Exception as e:
            logger.error("Database session error", error=str(e))
            await session.rollback()
            raise
        finally:
            await session.close()

    @classmethod
    @asynccontextmanager
    async def get_admin_session(cls) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an admin database session for write operations.

        This should be used only for system-managed writes (sessions/messages).
        """
        if cls._admin_session_factory is None:
            raise RuntimeError(
                "Admin database not initialized. Call DatabaseManager.initialize(use_readonly=False) first."
            )

        session = cls._admin_session_factory()
        try:
            yield session
        except Exception as e:
            logger.error("Admin database session error", error=str(e))
            await session.rollback()
            raise
        finally:
            await session.close()

    @classmethod
    async def health_check(cls) -> dict:
        """
        Check database connectivity and return health status.
        
        Returns:
            Dictionary with health status information.
        """
        result = {
            "status": "unknown",
            "readonly_connection": False,
            "table_count": 0,
            "error": None,
        }

        try:
            async with cls.get_readonly_session() as session:
                # Test connection
                await session.execute(text("SELECT 1"))
                result["readonly_connection"] = True

                # Get table count
                table_count_result = await session.execute(
                    text("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_type = 'BASE TABLE'
                    """)
                )
                result["table_count"] = table_count_result.scalar() or 0
                result["status"] = "healthy"

        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            logger.error("Database health check failed", error=str(e))

        return result


# Convenience functions for direct access
async def get_async_engine() -> AsyncEngine:
    """Get the read-only async engine."""
    return DatabaseManager.get_readonly_engine()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a read-only database session."""
    async with DatabaseManager.get_readonly_session() as session:
        yield session


async def get_admin_engine() -> AsyncEngine:
    """Get the admin async engine."""
    return DatabaseManager.get_admin_engine()


@asynccontextmanager
async def get_admin_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an admin database session."""
    async with DatabaseManager.get_admin_session() as session:
        yield session
