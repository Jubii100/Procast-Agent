"""Analysis endpoints for the Procast AI agent."""

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from src.agent.graph import get_agent, ProcastAgent
from src.api.middleware.auth import get_current_user, UserContext
from src.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ErrorResponse,
    SessionCreateResponse,
)
from src.core.config import settings
from src.sessions.repo import SessionRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Analyze budget data",
    description="Submit a natural language query to analyze budget data. "
                "The AI agent will interpret the query, generate appropriate SQL, "
                "execute it against the read-only database, and return analysis.",
)
async def analyze(
    request: AnalyzeRequest,
    user: UserContext = Depends(get_current_user),
) -> AnalyzeResponse:
    """
    Analyze budget data using natural language.
    
    This endpoint accepts a natural language query about budget data
    and returns an AI-generated analysis with recommendations.
    
    RLS scoping is applied based on the user's email/person_id.
    Messages and events are persisted to the session database.
    """
    logger.info(
        "Analyze request received",
        user_id=user.user_id,
        email=user.email,
        person_id=user.person_id,
        query_preview=request.query[:50],
    )
    
    try:
        # Get or create session for persistence
        session, was_created = await SessionRepository.get_or_create_session(
            session_id=request.session_id,
            user_id=user.user_id,
            email=user.email,
            person_id=user.person_id,
            company_id=user.company_id,
        )
        session_id = session.id
        
        # Log user message
        await SessionRepository.add_message(
            session_id=session_id,
            role="user",
            content=request.query,
            metadata={"context": request.context} if request.context else None,
        )
        
        # Get the agent
        agent = await get_agent()
        
        # Run the query with user context for RLS scoping
        result = await agent.query(
            question=request.query,
            user_id=user.user_id,
            session_id=session_id,
            email=user.email,
            person_id=user.person_id,
            company_id=user.company_id,
        )
        
        # Log assistant response
        response_text = result.get("response", "")
        if response_text:
            await SessionRepository.add_message(
                session_id=session_id,
                role="assistant",
                content=response_text,
                metadata={
                    "confidence": result.get("confidence"),
                    "row_count": result.get("row_count"),
                },
            )
        
        # Log events for agent behavior tracking
        if result.get("sql_query"):
            await SessionRepository.log_event(
                session_id=session_id,
                event_type="sql_generated",
                payload={
                    "sql": result.get("sql_query"),
                    "explanation": result.get("sql_explanation"),
                },
            )
        
        if result.get("metadata"):
            metadata = result.get("metadata", {})
            await SessionRepository.log_event(
                session_id=session_id,
                event_type="query_completed",
                payload={
                    "intent": metadata.get("intent"),
                    "domains": metadata.get("selected_domains"),
                    "llm_calls": metadata.get("total_llm_calls"),
                    "db_queries": metadata.get("total_db_queries"),
                    "confidence": result.get("confidence"),
                },
            )
        
        # Update session title if this is the first message
        if was_created and not session.title:
            # Use first 50 chars of query as title
            title = request.query[:50] + ("..." if len(request.query) > 50 else "")
            await SessionRepository.update_session_title(session_id, title)
        
        logger.info(
            "Analyze request completed",
            user_id=user.user_id,
            session_id=session_id,
            confidence=result.get("confidence"),
        )
        
        return AnalyzeResponse(
            response=result.get("response", ""),
            analysis=result.get("analysis"),
            recommendations=result.get("recommendations"),
            confidence=result.get("confidence", 0.0),
            data=result.get("data"),
            row_count=result.get("row_count", 0),
            session_id=session_id,
            sql_query=result.get("sql_query"),
            metadata=result.get("metadata"),
            error=result.get("error"),
        )
        
    except Exception as e:
        logger.error(
            "Analyze request failed",
            user_id=user.user_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )


@router.post(
    "/session",
    response_model=SessionCreateResponse,
    summary="Create a new session",
    description="Create a new conversation session for multi-turn interactions.",
)
async def create_session(
    user: UserContext = Depends(get_current_user),
) -> SessionCreateResponse:
    """Create a new conversation session."""
    import uuid
    
    session_id = str(uuid.uuid4())
    
    logger.info(
        "Session created",
        user_id=user.user_id,
        session_id=session_id,
    )
    
    return SessionCreateResponse(
        session_id=session_id,
        user_id=user.user_id,
        created_at=datetime.utcnow(),
    )


@router.get(
    "/quick-analysis/budgets",
    response_model=AnalyzeResponse,
    summary="Quick budget overview",
    description="Get a quick overview of all project budgets without a custom query.",
)
async def quick_budget_overview(
    user: UserContext = Depends(get_current_user),
    limit: int = Query(default=10, ge=1, le=100, description="Maximum projects to return"),
) -> AnalyzeResponse:
    """Get a quick budget overview."""
    return await analyze(
        request=AnalyzeRequest(
            query=f"Give me an overview of the top {limit} project budgets with their status"
        ),
        user=user,
    )


@router.get(
    "/quick-analysis/overspending",
    response_model=AnalyzeResponse,
    summary="Overspending alerts",
    description="Get alerts for projects that are overspending or at risk.",
)
async def quick_overspending_alerts(
    user: UserContext = Depends(get_current_user),
    threshold: float = Query(
        default=90.0,
        ge=0,
        le=200,
        description="Percentage threshold for at-risk status",
    ),
) -> AnalyzeResponse:
    """Get overspending alerts."""
    return await analyze(
        request=AnalyzeRequest(
            query=f"Show me projects that have spent more than {threshold}% of their budget, focusing on overspending risks"
        ),
        user=user,
    )


@router.get(
    "/quick-analysis/categories",
    response_model=AnalyzeResponse,
    summary="Category breakdown",
    description="Get spending breakdown by expense category.",
)
async def quick_category_breakdown(
    user: UserContext = Depends(get_current_user),
    top_n: int = Query(default=10, ge=1, le=50, description="Number of top categories"),
) -> AnalyzeResponse:
    """Get category spending breakdown."""
    return await analyze(
        request=AnalyzeRequest(
            query=f"Show me the top {top_n} spending categories with their amounts and percentages"
        ),
        user=user,
    )
