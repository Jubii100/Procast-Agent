"""DSPy signatures with field descriptions for Procast AI modules."""

import dspy


class SQLGeneratorSignature(dspy.Signature):
    """Generate a PostgreSQL SELECT query from a natural language question.
    
    You are a SQL expert working with a budget management database.
    Generate ONLY SELECT statements. Never generate INSERT, UPDATE, DELETE, or DDL.
    Always filter by IsDisabled = false for soft-deleted records.
    Use proper table aliases and explicit column names.
    
    CRITICAL - Revenue vs Expenses in EntryLines table:
    - IsComputedInverse = false → EXPENSES/COSTS (positive amounts)
    - IsComputedInverse = true → REVENUE/INCOME (stored as NEGATIVE amounts)
    
    For budget/cost/expense questions: WHERE IsComputedInverse = false
    For revenue/income questions: WHERE IsComputedInverse = true, use ABS() for positive values
    For comprehensive overview: separate expenses and revenue using CASE statements
    
    WARNING: Raw SUM without IsComputedInverse filter mixes revenue and expenses!
    """
    
    question: str = dspy.InputField(
        desc="The natural language question about budget/financial data"
    )
    schema_context: str = dspy.InputField(
        desc="Relevant database schema information including tables and relationships"
    )
    table_descriptions: str = dspy.InputField(
        desc="Descriptions of key tables and their columns"
    )
    
    sql_query: str = dspy.OutputField(
        desc="A valid PostgreSQL SELECT query that answers the question. "
             "Must be read-only (SELECT only). Include proper JOINs and WHERE clauses."
    )
    explanation: str = dspy.OutputField(
        desc="Brief explanation of what the query does and why it answers the question"
    )


class AnalysisSynthesizerSignature(dspy.Signature):
    """Synthesize financial analysis from database query results.
    
    You are a financial analyst reviewing budget data for event planning.
    Provide clear, actionable insights about spending, budgets, and trends.
    Flag any concerning patterns like overspending or unusual changes.
    """
    
    question: str = dspy.InputField(
        desc="The original question from the user"
    )
    query_results: str = dspy.InputField(
        desc="JSON data returned from the database query"
    )
    budget_context: str = dspy.InputField(
        desc="Additional context about the budget domain and business rules"
    )
    
    analysis: str = dspy.OutputField(
        desc="Clear, structured analysis of the data that answers the question. "
             "Include specific numbers, percentages, and comparisons where relevant."
    )
    recommendations: str = dspy.OutputField(
        desc="Actionable recommendations based on the analysis. "
             "Focus on budget optimization, risk mitigation, and best practices."
    )
    confidence: float = dspy.OutputField(
        desc="Confidence score from 0.0 to 1.0 indicating how well the data "
             "supports the analysis. Lower if data is incomplete or ambiguous."
    )


class IntentClassifierSignature(dspy.Signature):
    """Classify user intent for routing to appropriate handlers.
    
    Determine if the question requires database access, clarification,
    or can be answered with general information.
    """
    
    question: str = dspy.InputField(
        desc="The user's question or request"
    )
    conversation_history: str = dspy.InputField(
        desc="Previous messages in the conversation for context"
    )
    
    intent: str = dspy.OutputField(
        desc="One of: 'db_query' (needs database), 'clarify' (needs more info), "
             "'general_info' (can answer without database)"
    )
    requires_db_query: bool = dspy.OutputField(
        desc="True if the question requires querying the database"
    )
    clarification_needed: bool = dspy.OutputField(
        desc="True if the question is ambiguous and needs clarification"
    )
    clarification_questions: str = dspy.OutputField(
        desc="If clarification needed, what questions to ask the user"
    )


class QueryRefinementSignature(dspy.Signature):
    """Refine a SQL query based on validation feedback.
    
    Fix syntax errors, add missing clauses, or improve query structure.
    """
    
    original_query: str = dspy.InputField(
        desc="The original SQL query that needs refinement"
    )
    validation_error: str = dspy.InputField(
        desc="Error message or validation feedback"
    )
    schema_context: str = dspy.InputField(
        desc="Database schema information"
    )
    
    refined_query: str = dspy.OutputField(
        desc="Corrected SQL query that addresses the validation issues"
    )
    changes_made: str = dspy.OutputField(
        desc="Description of what was changed to fix the query"
    )


class SummarizationSignature(dspy.Signature):
    """Summarize complex analysis results into a concise response."""
    
    detailed_analysis: str = dspy.InputField(
        desc="The full detailed analysis"
    )
    user_expertise_level: str = dspy.InputField(
        desc="User's expertise level: 'technical', 'business', 'executive'"
    )
    
    summary: str = dspy.OutputField(
        desc="Concise summary appropriate for the user's expertise level"
    )
    key_metrics: str = dspy.OutputField(
        desc="Top 3-5 key metrics or findings as bullet points"
    )
