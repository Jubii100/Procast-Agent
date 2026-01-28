"""API route modules."""

from src.api.routes.analyze import router as analyze_router
from src.api.routes.schema import router as schema_router

__all__ = ["analyze_router", "schema_router"]
