"""Streaming LLM utilities for real-time token generation."""

import asyncio
from typing import AsyncGenerator, Optional, Any

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks import AsyncCallbackHandler

from src.core.config import settings

logger = structlog.get_logger(__name__)


class TokenStreamCallback(AsyncCallbackHandler):
    """Callback handler that captures streaming tokens."""

    def __init__(self):
        self.tokens: asyncio.Queue[str] = asyncio.Queue()
        self.done = False
        self.error: Optional[Exception] = None

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """Called when a new token is generated."""
        await self.tokens.put(token)

    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Called when LLM generation ends."""
        self.done = True
        await self.tokens.put("")  # Signal completion

    async def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        """Called when an error occurs."""
        self.error = error
        self.done = True
        await self.tokens.put("")  # Signal completion


def get_streaming_llm(
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> ChatAnthropic:
    """
    Get a streaming-enabled Anthropic LLM instance.
    
    Args:
        model: Model identifier (defaults to settings.llm_model)
        temperature: Temperature for generation
        max_tokens: Maximum tokens to generate
        
    Returns:
        ChatAnthropic instance configured for streaming
    """
    model = model or settings.llm_model
    
    return ChatAnthropic(
        model=model,
        anthropic_api_key=settings.anthropic_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=True,
    )


async def stream_analysis_response(
    question: str,
    query_results: str,
    schema_context: str,
    sql_query: str,
    conversation_history: Optional[list[dict]] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream an analysis response token by token.
    
    This is used for the streaming endpoint to provide real-time
    token output to the UI.
    
    Args:
        question: User's question
        query_results: JSON string of query results
        schema_context: Database schema context
        sql_query: The SQL query that was executed
        conversation_history: Optional previous messages
        
    Yields:
        Tokens as they are generated
    """
    llm = get_streaming_llm()
    callback = TokenStreamCallback()
    
    # Build the system prompt
    system_prompt = """You are Procast AI, a financial analysis assistant for event budget management.

You have just executed a database query and received results. Your task is to:
1. Analyze the query results
2. Provide clear, actionable insights
3. Highlight any risks or opportunities
4. Make recommendations where appropriate

Be concise but thorough. Use markdown formatting for clarity.
Format numbers with appropriate currency symbols and thousand separators.
If the results seem incomplete or unusual, note your confidence level."""

    # Build the user message with context
    user_content = f"""**User Question:** {question}

**SQL Query Executed:**
```sql
{sql_query}
```

**Query Results:**
```json
{query_results}
```

Please analyze these results and provide insights to answer the user's question."""

    messages = [
        SystemMessage(content=system_prompt),
    ]
    
    # Add conversation history if provided
    if conversation_history:
        for msg in conversation_history[-10:]:  # Last 10 messages for context
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg.get("content", "")))
    
    messages.append(HumanMessage(content=user_content))
    
    logger.info("Starting streaming analysis", question=question[:50])
    
    # Start streaming generation in background
    async def generate():
        try:
            await llm.ainvoke(
                messages,
                config={"callbacks": [callback]},
            )
        except Exception as e:
            callback.error = e
            callback.done = True
            await callback.tokens.put("")

    # Start generation task
    task = asyncio.create_task(generate())
    
    try:
        # Yield tokens as they arrive
        while True:
            try:
                token = await asyncio.wait_for(callback.tokens.get(), timeout=60.0)
                if callback.done and token == "":
                    break
                if token:
                    yield token
            except asyncio.TimeoutError:
                logger.warning("Streaming timeout")
                break
        
        # Check for errors
        if callback.error:
            yield f"\n\n[Error: {str(callback.error)}]"
            
    finally:
        # Ensure task completes
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def stream_simple_response(
    prompt: str,
    system_prompt: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream a simple LLM response.
    
    Args:
        prompt: The prompt to send
        system_prompt: Optional system prompt
        
    Yields:
        Tokens as they are generated
    """
    llm = get_streaming_llm()
    callback = TokenStreamCallback()
    
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=prompt))
    
    async def generate():
        try:
            await llm.ainvoke(
                messages,
                config={"callbacks": [callback]},
            )
        except Exception as e:
            callback.error = e
            callback.done = True
            await callback.tokens.put("")

    task = asyncio.create_task(generate())
    
    try:
        while True:
            try:
                token = await asyncio.wait_for(callback.tokens.get(), timeout=60.0)
                if callback.done and token == "":
                    break
                if token:
                    yield token
            except asyncio.TimeoutError:
                break
                
        if callback.error:
            yield f"\n\n[Error: {str(callback.error)}]"
            
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
