"""LangGraph node functions for the Procast AI agent."""

from datetime import datetime
from typing import Any

import structlog

from src.agent.state import AgentState, add_assistant_message, format_conversation_history
from src.dspy_modules.classifier import IntentClassifier
from src.dspy_modules.sql_generator import SQLGenerator
from src.dspy_modules.analyzer import AnalysisSynthesizer
from src.dspy_modules.table_selector import TableSelector
from src.db.schema_registry import build_schema_context, get_db_summary
from src.mcp.tools import DatabaseTools, SQLValidator
from src.db.connection import DatabaseManager

logger = structlog.get_logger(__name__)

# Instantiate DSPy modules (they're stateless, so can be shared)
_intent_classifier = None
_sql_generator = None
_analyzer = None
_table_selector = None


def _get_classifier() -> IntentClassifier:
    """Lazy-load the intent classifier."""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier()
    return _intent_classifier


def _get_sql_generator() -> SQLGenerator:
    """Lazy-load the SQL generator."""
    global _sql_generator
    if _sql_generator is None:
        _sql_generator = SQLGenerator()
    return _sql_generator


def _get_analyzer() -> AnalysisSynthesizer:
    """Lazy-load the analyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalysisSynthesizer()
    return _analyzer


def _get_table_selector() -> TableSelector:
    """Lazy-load the table selector (uses cheap LLM model)."""
    global _table_selector
    if _table_selector is None:
        _table_selector = TableSelector()
    return _table_selector


async def classify_intent_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Classify user intent.
    
    Determines if the query needs database access, clarification,
    or can be answered with general information.
    """
    logger.info("Classifying intent", session_id=state["session_id"])
    
    # Get the last user message
    user_message = state["messages"][-1]["content"]
    conversation_history = format_conversation_history(state["messages"][:-1])
    
    try:
        classifier = _get_classifier()
        result = classifier(
            question=user_message,
            conversation_history=conversation_history,
        )
        
        logger.info(
            "Intent classified",
            intent=result.intent,
            requires_db=result.requires_db_query,
        )
        
        return {
            "intent": result.intent,
            "requires_db_query": result.requires_db_query,
            "clarification_needed": result.clarification_needed,
            "clarification_questions": result.clarification_questions,
            "total_llm_calls": state["total_llm_calls"] + 1,
        }
        
    except Exception as e:
        logger.error("Intent classification failed", error=str(e))
        return {
            "intent": "db_query",  # Default to db_query
            "requires_db_query": True,
            "clarification_needed": False,
            "error": f"Intent classification failed: {str(e)}",
        }


async def select_tables_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Select relevant database domains for the query.
    
    Uses a cheap LLM model (claude-3-5-haiku) to intelligently select
    which domains are needed for the query. This minimizes token usage
    in the main SQL generation step by only loading relevant schemas.
    """
    logger.info("Selecting relevant domains", session_id=state["session_id"])
    
    user_message = state["messages"][-1]["content"]
    
    try:
        selector = _get_table_selector()
        result = selector(question=user_message)
        
        # Build schema context for selected domains
        domains = result.selected_domains
        schema_context = build_schema_context(domains)
        
        logger.info(
            "Domains selected",
            domains=domains,
            token_estimate=schema_context.token_estimate,
            reasoning=result.reasoning[:100] if result.reasoning else None,
        )
        
        return {
            "selected_domains": domains,
            "schema_context": schema_context.full_context,
            "domain_selection_reasoning": result.reasoning,
            "total_llm_calls": state["total_llm_calls"] + 1,
        }
        
    except Exception as e:
        logger.error("Table selection failed", error=str(e))
        # Fallback to base domains
        base_domains = ["projects", "budgets"]
        fallback_context = build_schema_context(base_domains)
        return {
            "selected_domains": base_domains,
            "schema_context": fallback_context.full_context,
            "domain_selection_reasoning": "Fallback to base domains due to error",
        }


async def generate_sql_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Generate SQL query from natural language.
    
    Uses the selected domains' schema context for cost-efficient,
    accurate SQL generation.
    """
    logger.info("Generating SQL", session_id=state["session_id"])
    
    user_message = state["messages"][-1]["content"]
    schema_context = state.get("schema_context") or ""
    
    # If no schema context, we need to select tables first
    if not schema_context:
        logger.warning("No schema context available, using minimal context")
        minimal_context = build_schema_context(["projects", "budgets"])
        schema_context = minimal_context.full_context
    
    try:
        generator = _get_sql_generator()
        
        # If there's a previous validation error, use refinement
        if state.get("sql_validation_error"):
            result = generator.forward_with_refinement(
                question=user_message,
                validation_error=state["sql_validation_error"],
                schema_context=schema_context,
                table_descriptions="",  # Already included in schema_context
            )
        else:
            result = generator(
                question=user_message,
                schema_context=schema_context,
                table_descriptions="",  # Already included in schema_context
            )
        
        logger.info(
            "SQL generated",
            sql_preview=result.sql_query[:100] if result.sql_query else None,
        )
        
        return {
            "generated_sql": result.sql_query,
            "sql_explanation": result.explanation,
            "sql_validation_error": None,  # Clear previous error
            "total_llm_calls": state["total_llm_calls"] + 1,
        }
        
    except Exception as e:
        logger.error("SQL generation failed", error=str(e))
        return {
            "error": f"SQL generation failed: {str(e)}",
            "error_type": "sql_generation",
        }


async def validate_sql_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Validate the generated SQL query.
    
    Ensures only SELECT statements pass through.
    """
    logger.info("Validating SQL", session_id=state["session_id"])
    
    sql = state.get("generated_sql")
    if not sql:
        return {
            "sql_validation_error": "No SQL query generated",
            "sql_retry_count": state["sql_retry_count"] + 1,
        }
    
    is_valid, error = SQLValidator.validate(sql)
    
    if is_valid:
        logger.info("SQL validation passed")
        return {
            "sql_validation_error": None,
        }
    else:
        logger.warning("SQL validation failed", error=error)
        return {
            "sql_validation_error": error,
            "sql_retry_count": state["sql_retry_count"] + 1,
        }


async def execute_query_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Execute the validated SQL query.
    
    Uses the read-only database connection.
    """
    logger.info("Executing query", session_id=state["session_id"])
    
    sql = state.get("generated_sql")
    if not sql:
        return {
            "query_error": "No SQL query to execute",
        }
    
    try:
        async with DatabaseManager.get_readonly_session() as session:
            tools = DatabaseTools(session)
            result = await tools.execute_query(sql=sql)
            
            if result.success:
                logger.info(
                    "Query executed",
                    row_count=result.row_count,
                )
                return {
                    "query_results": result.data,
                    "query_row_count": result.row_count,
                    "query_error": None,
                    "total_db_queries": state["total_db_queries"] + 1,
                }
            else:
                logger.warning("Query execution failed", error=result.error)
                return {
                    "query_error": result.error,
                    "sql_validation_error": result.error,  # Trigger retry
                    "sql_retry_count": state["sql_retry_count"] + 1,
                }
                
    except Exception as e:
        logger.error("Query execution error", error=str(e))
        return {
            "query_error": str(e),
            "error": f"Database query failed: {str(e)}",
            "error_type": "query_execution",
        }


async def analyze_results_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Analyze query results and generate insights.
    
    Uses DSPy analyzer to synthesize financial analysis.
    """
    logger.info("Analyzing results", session_id=state["session_id"])
    
    user_message = state["messages"][-1]["content"]
    query_results = state.get("query_results", [])
    
    if not query_results:
        return {
            "analysis": "No data was returned from the query.",
            "recommendations": "Try rephrasing your question or specifying a different time period or project.",
            "confidence": 0.3,
        }
    
    try:
        analyzer = _get_analyzer()
        result = analyzer(
            question=user_message,
            query_results=query_results,
        )
        
        logger.info(
            "Analysis completed",
            confidence=result.confidence,
        )
        
        return {
            "analysis": result.analysis,
            "recommendations": result.recommendations,
            "confidence": result.confidence,
            "total_llm_calls": state["total_llm_calls"] + 1,
        }
        
    except Exception as e:
        logger.error("Analysis failed", error=str(e))
        return {
            "error": f"Analysis failed: {str(e)}",
            "error_type": "analysis",
        }


async def format_response_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Format the final response to the user.
    
    Combines analysis, recommendations, and metadata into a response.
    """
    logger.info("Formatting response", session_id=state["session_id"])
    
    # Build the response
    parts = []
    
    # Add analysis
    if state.get("analysis"):
        parts.append(state["analysis"])
    
    # Add recommendations
    if state.get("recommendations"):
        parts.append("\n### Recommendations\n")
        parts.append(state["recommendations"])
    
    # Add confidence indicator
    confidence = state.get("confidence", 0.0)
    if confidence < 0.7:
        parts.append(f"\n\n*Note: Confidence level is {confidence:.0%}. Results may be incomplete or require verification.*")
    
    response = "\n".join(parts)
    
    # Add as assistant message
    message_update = add_assistant_message(state, response)
    
    return {
        "response": response,
        "processing_completed": datetime.utcnow().isoformat(),
        **message_update,
    }


async def handle_clarification_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Handle requests that need clarification.
    
    Returns clarifying questions to the user.
    """
    logger.info("Handling clarification", session_id=state["session_id"])
    
    questions = state.get("clarification_questions", "")
    if not questions:
        questions = "Could you please provide more details about what you'd like to know?"
    
    response = f"I need a bit more information to help you:\n\n{questions}"
    message_update = add_assistant_message(state, response)
    
    return {
        "response": response,
        "processing_completed": datetime.utcnow().isoformat(),
        **message_update,
    }


async def handle_general_info_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Handle general information requests.
    
    Provides information about the system without database queries.
    """
    logger.info("Handling general info", session_id=state["session_id"])
    
    # Get compact DB summary for context
    db_summary = get_db_summary()
    
    response = f"""I can help you with budget analysis for your Procast events. Here's what I can do:

**Budget Analysis:**
- View project budget summaries
- Identify overspending or at-risk budgets
- Analyze spending by category
- Track budget changes over time
- Compare budgets vs actuals (invoices/POs)

**Available Data Domains:**
{db_summary.split('DOMAINS:')[1].split('KEY FACTS')[0].strip() if 'DOMAINS:' in db_summary else '- Projects, Budgets, Accounts, Invoices, and more'}

Please ask a specific question about your budget data, and I'll query the database to provide insights."""

    message_update = add_assistant_message(state, response)
    
    return {
        "response": response,
        "processing_completed": datetime.utcnow().isoformat(),
        **message_update,
    }


async def handle_error_node(state: AgentState) -> dict[str, Any]:
    """
    Node: Handle errors gracefully.
    
    Returns a user-friendly error message.
    """
    logger.info("Handling error", session_id=state["session_id"], error=state.get("error"))
    
    error_type = state.get("error_type", "unknown")
    error = state.get("error", "An unexpected error occurred")
    
    if error_type == "sql_generation":
        response = "I had trouble understanding how to query the database for your request. Could you try rephrasing your question?"
    elif error_type == "query_execution":
        response = "There was an issue executing the database query. This might be due to a temporary issue. Please try again."
    elif error_type == "analysis":
        response = "I was able to get the data but had trouble analyzing it. Here's what I found:\n\n" + str(state.get("query_results", [])[:5])
    else:
        response = f"I encountered an issue: {error}\n\nPlease try again or rephrase your question."
    
    message_update = add_assistant_message(state, response)
    
    return {
        "response": response,
        "processing_completed": datetime.utcnow().isoformat(),
        **message_update,
    }
