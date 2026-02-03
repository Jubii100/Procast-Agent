"""Streaming endpoint for real-time analysis responses."""

import json
from typing import AsyncGenerator, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.middleware.auth import get_current_user, UserContext
from src.api.schemas import AnalyzeRequest
from src.api.streaming import stream_analysis_response
from src.sessions.repo import SessionRepository
from src.db.connection import DatabaseManager
from src.mcp.tools import DatabaseTools
from src.dspy_modules.table_selector import TableSelector
from src.dspy_modules.classifier import IntentClassifier
from src.dspy_modules.config import get_configured_lm
from src.dspy_modules.sql_generator import SQLGenerator
from src.db.schema_registry import build_schema_context, get_db_summary

logger = structlog.get_logger(__name__)


# Friendly chat responses for streaming
FRIENDLY_RESPONSES = {
    "greeting": "Hello! I'm Procast AI, your budget analysis assistant. How can I help you with your event budget data today?",
    "how_are_you": "I'm doing great, thank you for asking! I'm here and ready to help you analyze your budget data. What would you like to know?",
    "thanks": "You're welcome! If you have any more questions about your budget data, feel free to ask.",
    "goodbye": "Goodbye! Feel free to come back anytime you need help with budget analysis.",
    "default": "Hello! I'm Procast AI, your budget analysis assistant. I can help you analyze project budgets, identify spending patterns, and provide financial insights. What would you like to know about your budget data?",
}


def get_friendly_response(query: str) -> str:
    """Get appropriate friendly response based on query content."""
    query_lower = query.lower().strip()
    
    if any(g in query_lower for g in ["hi", "hello", "hey", "greetings"]):
        return FRIENDLY_RESPONSES["greeting"]
    elif any(p in query_lower for p in ["how are you", "how's it going", "what's up"]):
        return FRIENDLY_RESPONSES["how_are_you"]
    elif any(p in query_lower for p in ["thank", "thanks", "appreciate"]):
        return FRIENDLY_RESPONSES["thanks"]
    elif any(p in query_lower for p in ["bye", "goodbye", "see you", "later"]):
        return FRIENDLY_RESPONSES["goodbye"]
    else:
        return FRIENDLY_RESPONSES["default"]

router = APIRouter(prefix="/api/v1", tags=["Streaming"])


async def generate_sse_response(
    request: AnalyzeRequest,
    user: UserContext,
) -> AsyncGenerator[str, None]:
    """
    Generate Server-Sent Events with real-time token streaming.
    
    Yields SSE formatted events:
    - event: session (session info)
    - event: status (processing updates)
    - event: token (real-time tokens from LLM)
    - event: complete (final metadata)
    - event: error (if an error occurs)
    """
    session_id = None
    full_response = ""
    sql_query = None
    try:
        # Get or create session
        session, was_created = await SessionRepository.get_or_create_session(
            session_id=request.session_id,
            user_id=user.user_id,
            email=user.email,
            person_id=user.person_id,
            company_id=user.company_id,
        )
        session_id = session.id
        
        # Send session info
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"
        
        # Log user message
        await SessionRepository.add_message(
            session_id=session_id,
            role="user",
            content=request.query,
        )
        
        # Phase 0: Intent classification (to handle friendly chat and non-DB queries)
        yield f"event: status\ndata: {json.dumps({'status': 'classifying', 'message': 'Understanding your request...'})}\n\n"
        
        classifier = IntentClassifier()
        intent_result = classifier(question=request.query, conversation_history="")
        intent = intent_result.intent
        
        logger.info("Intent classified", intent=intent, query=request.query[:50])
        
        # Handle non-DB intents without SQL generation
        if intent == "friendly_chat":
            # Stream a friendly response directly
            friendly_response = get_friendly_response(request.query)
            
            for token in friendly_response.split():
                yield f"event: token\ndata: {json.dumps({'token': token + ' '})}\n\n"
                full_response += token + " "
            
            # Log assistant response
            await SessionRepository.add_message(
                session_id=session_id,
                role="assistant",
                content=full_response.strip(),
            )
            
            yield f"event: complete\ndata: {json.dumps({'session_id': session_id, 'intent': 'friendly_chat', 'row_count': 0})}\n\n"
            return
        
        elif intent == "general_info":
            # Provide general info about the system
            db_summary = get_db_summary()
            info_response = f"""I can help you with budget analysis for your Procast events. Here's what I can do:

**Budget Analysis:**
- View project budget summaries
- Identify overspending or at-risk budgets
- Analyze spending by category
- Track budget changes over time
- Compare budgets vs actuals (invoices/POs)

Please ask a specific question about your budget data, and I'll query the database to provide insights."""
            
            for token in info_response.split():
                yield f"event: token\ndata: {json.dumps({'token': token + ' '})}\n\n"
                full_response += token + " "
            
            await SessionRepository.add_message(
                session_id=session_id,
                role="assistant",
                content=full_response.strip(),
            )
            
            yield f"event: complete\ndata: {json.dumps({'session_id': session_id, 'intent': 'general_info', 'row_count': 0})}\n\n"
            return
        
        elif intent == "clarify":
            # Need clarification
            clarify_response = intent_result.clarification_questions or "Could you please provide more details about what you'd like to know?"
            clarify_full = f"I need a bit more information to help you:\n\n{clarify_response}"
            
            for token in clarify_full.split():
                yield f"event: token\ndata: {json.dumps({'token': token + ' '})}\n\n"
                full_response += token + " "
            
            await SessionRepository.add_message(
                session_id=session_id,
                role="assistant",
                content=full_response.strip(),
            )
            
            yield f"event: complete\ndata: {json.dumps({'session_id': session_id, 'intent': 'clarify', 'row_count': 0})}\n\n"
            return
        
        # Phase 1: Domain selection (for db_query intent)
        yield f"event: status\ndata: {json.dumps({'status': 'selecting_domains', 'message': 'Identifying relevant data domains...'})}\n\n"
        
        selector = TableSelector()
        domain_result = selector(question=request.query)
        domains = domain_result.selected_domains
        
        # Phase 2: Build schema context
        yield f"event: status\ndata: {json.dumps({'status': 'loading_schema', 'message': 'Loading database schema...'})}\n\n"
        
        schema_context = build_schema_context(domains)
        
        # Phase 3: Generate SQL
        yield f"event: status\ndata: {json.dumps({'status': 'generating_sql', 'message': 'Generating SQL query...'})}\n\n"
        
        get_configured_lm()
        generator = SQLGenerator()
        sql_result = generator(
            question=request.query,
            schema_context=schema_context.full_context,
        )
        sql_query = sql_result.sql_query
        
        # Send SQL to client
        yield f"event: sql\ndata: {json.dumps({'sql': sql_query})}\n\n"
        
        # Log SQL generation event
        await SessionRepository.log_event(
            session_id=session_id,
            event_type="sql_generated",
            payload={"sql": sql_query, "domains": domains},
        )
        
        # Phase 4: Execute query with RLS scoping
        yield f"event: status\ndata: {json.dumps({'status': 'executing_query', 'message': 'Executing database query...'})}\n\n"
        
        async with DatabaseManager.get_scoped_session(
            person_id=user.person_id,
            email=user.email,
        ) as db_session:
            tools = DatabaseTools(db_session)
            query_result = await tools.execute_query(
                sql=sql_query,
                user_context={
                    "user_id": user.user_id,
                    "person_id": user.person_id,
                    "email": user.email,
                },
            )
        if not query_result.success:
            yield f"event: error\ndata: {json.dumps({'error': query_result.error, 'session_id': session_id})}\n\n"
            return
        
        # Send row count
        yield f"event: status\ndata: {json.dumps({'status': 'analyzing', 'message': f'Analyzing {query_result.row_count} rows...', 'row_count': query_result.row_count})}\n\n"
        
        # Phase 5: Stream analysis response
        query_results_json = json.dumps(query_result.data[:50], default=str)  # Limit for context
        
        # Stream real tokens from LLM
        async for token in stream_analysis_response(
            question=request.query,
            query_results=query_results_json,
            schema_context=schema_context.full_context,
            sql_query=sql_query,
        ):
            full_response += token
            yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
        
        # Log assistant response
        if full_response:
            await SessionRepository.add_message(
                session_id=session_id,
                role="assistant",
                content=full_response,
                metadata={
                    "row_count": query_result.row_count,
                    "domains": domains,
                },
            )
        
        # Log completion event
        await SessionRepository.log_event(
            session_id=session_id,
            event_type="stream_completed",
            payload={
                "row_count": query_result.row_count,
                "response_length": len(full_response),
                "domains": domains,
            },
        )
        
        # Update session title if first message
        if was_created:
            title = request.query[:50] + ("..." if len(request.query) > 50 else "")
            await SessionRepository.update_session_title(session_id, title)
        
        # Send complete event
        complete_data = {
            "session_id": session_id,
            "sql_query": sql_query,
            "row_count": query_result.row_count,
            "domains": domains,
            "response_length": len(full_response),
        }
        yield f"event: complete\ndata: {json.dumps(complete_data)}\n\n"
        
    except Exception as e:
        logger.error("Streaming analysis failed", error=str(e), session_id=session_id)
        error_data = {"error": str(e), "session_id": session_id}
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"


@router.post(
    "/analyze/stream",
    summary="Stream analysis response",
    description="Submit a query and receive real-time streaming SSE events with tokens as they are generated.",
)
async def stream_analyze(
    request: AnalyzeRequest,
    user: UserContext = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream analysis response using Server-Sent Events with real-time tokens.
    
    Events:
    - session: Session ID for the conversation
    - status: Processing status updates (domain selection, SQL generation, etc.)
    - sql: The generated SQL query
    - token: Real-time response tokens from LLM
    - complete: Final metadata when streaming completes
    - error: Error information if something fails
    """
    logger.info(
        "Stream analyze request received",
        user_id=user.user_id,
        email=user.email,
        query_preview=request.query[:50],
    )
    
    return StreamingResponse(
        generate_sse_response(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
