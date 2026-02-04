"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.middleware.auth import AuthMiddleware
from src.api.routes.analyze import router as analyze_router
from src.api.routes.chat import router as chat_router
from src.api.routes.schema import router as schema_router
from src.api.routes.sessions import router as sessions_router
from src.api.schemas import HealthResponse, ErrorResponse
from src.agent.graph import get_agent
from src.core.config import settings
from src.db.connection import DatabaseManager
from src.sessions.db import ensure_chat_tables

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Procast AI API")
    
    try:
        # Initialize database (read-only + admin for writes)
        await DatabaseManager.initialize(use_readonly=False)
        logger.info("Database initialized")

        # Ensure chat session tables exist
        await ensure_chat_tables()
        logger.info("Chat session tables ready")
        
        # Pre-initialize agent (optional, for faster first request)
        # agent = await get_agent()
        # logger.info("Agent initialized")
        
    except Exception as e:
        logger.error("Startup failed", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Procast AI API")
    await DatabaseManager.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Procast AI Agent",
        description="""
# Procast AI Budget Analysis Agent

AI-powered budget analysis for event planning and management.

## Features

- **Natural Language Queries**: Ask questions about your budget data in plain English
- **Intelligent Analysis**: Get AI-generated insights and recommendations
- **Safe Read-Only Access**: All database queries are read-only and validated

## Authentication

JWT Bearer tokens via the `Authorization` header.

## Quick Start

1. Use the `/api/v1/analyze` endpoint with a `POST` request
2. Include your question in the `query` field
3. Receive AI-generated analysis with data and recommendations

## Example

```json
POST /api/v1/analyze
{
    "query": "What is the budget status for all projects?"
}
```
        """,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add auth middleware
    app.add_middleware(AuthMiddleware)
    
    # Include routers
    app.include_router(analyze_router)
    app.include_router(schema_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    
    # Health check endpoint
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="Health check",
        description="Check the health status of the API and its dependencies.",
    )
    async def health_check() -> HealthResponse:
        """Check API health status."""
        # Check database
        db_health = await DatabaseManager.health_check()
        
        # Check agent (don't initialize, just check status)
        agent_status = {
            "status": "ready",
            "llm_configured": bool(settings.anthropic_api_key),
        }
        
        overall_status = "healthy" if db_health["status"] == "healthy" else "unhealthy"
        
        return HealthResponse(
            status=overall_status,
            database=db_health,
            agent=agent_status,
            timestamp=datetime.now(timezone.utc),
        )
    
    # Error handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle uncaught exceptions."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal error occurred",
                "error_type": type(exc).__name__,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    
    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level=settings.log_level.lower(),
    )
