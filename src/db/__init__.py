"""Database module for Procast AI."""

from src.db.connection import (
    get_async_engine,
    get_async_session,
    get_scoped_async_session,
    lookup_person_by_email,
    DatabaseManager,
)
from src.db.schema_registry import (
    get_db_summary,
    get_all_domains,
    get_domain_schema,
    build_schema_context,
    SchemaContext,
)

__all__ = [
    "get_async_engine",
    "get_async_session",
    "get_scoped_async_session",
    "lookup_person_by_email",
    "DatabaseManager",
    "get_db_summary",
    "get_all_domains",
    "get_domain_schema",
    "build_schema_context",
    "SchemaContext",
]
