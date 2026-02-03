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


async def lookup_person_by_email(session: AsyncSession, email: str) -> Optional[dict]:
    """
    Look up a person by email address.
    
    Args:
        session: Database session
        email: User's email address
        
    Returns:
        Dict with person_id and company_id, or None if not found
    """
    try:
        result = await session.execute(
            text("""
                SELECT "Id" as person_id, "CompanyId" as company_id, "Email" as email
                FROM "People"
                WHERE LOWER("Email") = LOWER(:email)
                  AND "IsDisabled" = false
                LIMIT 1
            """),
            {"email": email}
        )
        row = result.mappings().first()
        if row:
            return {
                "person_id": str(row["person_id"]),
                "company_id": str(row["company_id"]) if row["company_id"] else None,
                "email": row["email"],
            }
        return None
    except Exception as e:
        logger.error("Failed to lookup person by email", email=email, error=str(e))
        return None


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
            use_readonly: If True, initializes the read-only connection for AI agent.
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

        # Optionally create admin engine (for setup scripts, not for AI agent)
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
    async def get_scoped_session(
        cls,
        person_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a read-only database session with RLS scope set.
        
        This session sets the app.current_person_id session variable
        which is used by PostgreSQL RLS policies to filter data.
        
        Args:
            person_id: The person's UUID (preferred if known)
            email: The person's email (used to lookup person_id if not provided)
            
        Yields:
            AsyncSession with RLS context set
            
        Raises:
            RuntimeError: If database not initialized
            ValueError: If neither person_id nor email provided, or email not found
        """
        if cls._readonly_session_factory is None:
            raise RuntimeError(
                "Database not initialized. Call DatabaseManager.initialize() first."
            )

        session = cls._readonly_session_factory()
        try:
            resolved_person_id = person_id
            
            # If no person_id, look up by email
            if not resolved_person_id and email:
                person_info = await lookup_person_by_email(session, email)
                if person_info:
                    resolved_person_id = person_info["person_id"]
                    logger.debug(
                        "Resolved person_id from email",
                        email=email,
                        person_id=resolved_person_id,
                    )
                else:
                    logger.warning(
                        "Could not find person by email, RLS will deny all access",
                        email=email,
                    )
            
            # Set the session variable for RLS policies
            # Note: SET command doesn't support parameterized queries in PostgreSQL
            # We validate the UUID format before interpolating to prevent SQL injection
            if resolved_person_id:
                # Validate UUID format to prevent SQL injection
                import uuid as uuid_module
                try:
                    # This will raise ValueError if not a valid UUID
                    uuid_module.UUID(resolved_person_id)
                    # Safe to interpolate since we validated it's a UUID
                    await session.execute(
                        text(f"SET app.current_person_id = '{resolved_person_id}'")
                    )
                    logger.debug(
                        "Set RLS context",
                        person_id=resolved_person_id,
                    )
                except ValueError:
                    logger.error(
                        "Invalid person_id format, not a valid UUID",
                        person_id=resolved_person_id,
                    )
                    await session.execute(text("SET app.current_person_id = ''"))
            else:
                # Set empty string so RLS policies deny all access
                await session.execute(text("SET app.current_person_id = ''"))
                logger.warning(
                    "No person_id available, RLS will deny all access",
                )
            
            yield session
            
        except Exception as e:
            logger.error("Scoped session error", error=str(e))
            await session.rollback()
            raise
        finally:
            # Reset the session variable before closing
            try:
                await session.execute(text("RESET app.current_person_id"))
            except Exception:
                pass  # Ignore errors during cleanup
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


@asynccontextmanager
async def get_scoped_async_session(
    person_id: Optional[str] = None,
    email: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get a read-only database session with RLS scope.
    
    Args:
        person_id: The person's UUID (preferred)
        email: The person's email (used for lookup if person_id not provided)
    """
    async with DatabaseManager.get_scoped_session(
        person_id=person_id,
        email=email,
    ) as session:
        yield session
