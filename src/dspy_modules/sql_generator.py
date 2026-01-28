"""SQL Generator DSPy module for Procast AI."""

from typing import Optional

import dspy
import structlog

from src.dspy_modules.signatures import (
    SQLGeneratorSignature,
    QueryRefinementSignature,
)
from src.db.schema_registry import build_schema_context

logger = structlog.get_logger(__name__)

# Minimal fallback context for when no schema is provided
MINIMAL_SCHEMA_CONTEXT = """
PROCAST DATABASE - Event Budget Management System

Core Tables:
- Projects: Events/projects with Brand, TakePlaceDate, OperatingCurrencyId
- ProjectAccounts: Links projects to accounts
- EntryLines: Budget line items with Amount, Quantity, Status (≥2 = committed)
- Accounts: Chart of accounts with Number, Description
- AccountCategories: Hierarchical expense categories

Key Rules:
- Budget total = SUM(Amount × Quantity)
- Always filter: IsDisabled = false
- Exclude scenarios: WHERE OriginalProjectId IS NULL
"""


class SQLGenerator(dspy.Module):
    """
    Generates PostgreSQL SELECT queries from natural language questions.
    
    This module uses Chain-of-Thought prompting to reason about the
    database schema and generate appropriate SQL queries.
    
    Uses dynamically-loaded schema context for cost efficiency.
    """

    def __init__(self, max_refinement_attempts: int = 2):
        """
        Initialize the SQL generator.
        
        Args:
            max_refinement_attempts: Maximum attempts to refine invalid queries
        """
        super().__init__()
        self.max_refinement_attempts = max_refinement_attempts
        
        # Main SQL generation with Chain-of-Thought
        self.generate = dspy.ChainOfThought(SQLGeneratorSignature)
        
        # Query refinement for fixing invalid queries
        self.refine = dspy.ChainOfThought(QueryRefinementSignature)

    def forward(
        self,
        question: str,
        schema_context: Optional[str] = None,
        table_descriptions: Optional[str] = None,
    ) -> dspy.Prediction:
        """
        Generate a SQL query for the given question.
        
        Args:
            question: Natural language question about the data
            schema_context: Database schema information (dynamically loaded by agent)
            table_descriptions: Additional table descriptions (can be empty if included in schema_context)
            
        Returns:
            Prediction with sql_query and explanation fields
        """
        # Use minimal fallback if no context provided
        if not schema_context:
            logger.warning("No schema context provided, using minimal fallback")
            schema_context = MINIMAL_SCHEMA_CONTEXT
        
        # table_descriptions can be empty if already included in schema_context
        table_descriptions = table_descriptions or ""
        
        logger.info("Generating SQL query", question=question[:100])
        
        # Generate the query
        result = self.generate(
            question=question,
            schema_context=schema_context,
            table_descriptions=table_descriptions,
        )
        
        logger.debug(
            "SQL generated",
            sql=result.sql_query[:200] if result.sql_query else None,
            explanation=result.explanation[:100] if result.explanation else None,
        )
        
        return result

    def forward_with_refinement(
        self,
        question: str,
        validation_error: Optional[str] = None,
        schema_context: Optional[str] = None,
        table_descriptions: Optional[str] = None,
    ) -> dspy.Prediction:
        """
        Generate a SQL query with automatic refinement if validation fails.
        
        Args:
            question: Natural language question
            validation_error: Error from previous validation attempt
            schema_context: Database schema information
            table_descriptions: Additional table descriptions
            
        Returns:
            Prediction with sql_query and explanation
        """
        if not schema_context:
            schema_context = MINIMAL_SCHEMA_CONTEXT
        table_descriptions = table_descriptions or ""
        
        # If we have a validation error, try to refine
        if validation_error:
            logger.info("Refining SQL query", error=validation_error[:100])
            
            # First, generate initial query
            initial_result = self.generate(
                question=question,
                schema_context=schema_context,
                table_descriptions=table_descriptions,
            )
            
            # Then refine based on error
            refined_result = self.refine(
                original_query=initial_result.sql_query,
                validation_error=validation_error,
                schema_context=schema_context,
            )
            
            return dspy.Prediction(
                sql_query=refined_result.refined_query,
                explanation=f"{initial_result.explanation}\n\nRefined: {refined_result.changes_made}",
            )
        
        # No error, just generate normally
        return self.forward(
            question=question,
            schema_context=schema_context,
            table_descriptions=table_descriptions,
        )


class SQLGeneratorWithExamples(dspy.Module):
    """
    SQL Generator with few-shot examples for better accuracy.
    
    This variant includes demonstrations of good SQL queries
    for common budget analysis patterns.
    """

    # Few-shot examples for budget analysis - MUST filter by IsComputedInverse
    EXAMPLES = [
        dspy.Example(
            question="What is the total budget for all projects?",
            schema_context="[Schema provided dynamically]",
            table_descriptions="",
            sql_query='''
SELECT 
    COUNT(DISTINCT p."Id") as project_count,
    SUM(el."Amount" * el."Quantity") as total_expenses
FROM "Projects" p
JOIN "ProjectAccounts" pa ON pa."ProjectId" = p."Id" AND pa."IsDisabled" = false
JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id" AND el."IsDisabled" = false
WHERE p."IsDisabled" = false
AND p."OriginalProjectId" IS NULL
AND el."IsComputedInverse" = false
            '''.strip(),
            explanation="Sums EXPENSE entry lines (IsComputedInverse=false) across all active projects. Revenue entries are excluded."
        ).with_inputs("question", "schema_context", "table_descriptions"),
        
        dspy.Example(
            question="Give me a comprehensive overview of revenue vs expenses",
            schema_context="[Schema provided dynamically]",
            table_descriptions="",
            sql_query='''
SELECT 
    COUNT(DISTINCT p."Id") as project_count,
    SUM(CASE WHEN el."IsComputedInverse" = false THEN el."Amount" * el."Quantity" ELSE 0 END) as total_expenses,
    ABS(SUM(CASE WHEN el."IsComputedInverse" = true THEN el."Amount" * el."Quantity" ELSE 0 END)) as total_revenue,
    ABS(SUM(CASE WHEN el."IsComputedInverse" = true THEN el."Amount" * el."Quantity" ELSE 0 END)) - 
    SUM(CASE WHEN el."IsComputedInverse" = false THEN el."Amount" * el."Quantity" ELSE 0 END) as net_profit
FROM "Projects" p
JOIN "ProjectAccounts" pa ON pa."ProjectId" = p."Id" AND pa."IsDisabled" = false
JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id" AND el."IsDisabled" = false
WHERE p."IsDisabled" = false
AND p."OriginalProjectId" IS NULL
            '''.strip(),
            explanation="Separates expenses (IsComputedInverse=false) from revenue (IsComputedInverse=true, stored as negative). Calculates net profit."
        ).with_inputs("question", "schema_context", "table_descriptions"),
        
        dspy.Example(
            question="Which categories have the highest spending?",
            schema_context="[Schema provided dynamically]",
            table_descriptions="",
            sql_query='''
SELECT 
    ac."Name" as category_name,
    COUNT(el."Id") as entry_count,
    SUM(el."Amount" * el."Quantity") as total_spending
FROM "AccountCategories" ac
JOIN "Accounts" a ON a."SubAccountCategoryId" = ac."Id"
JOIN "LegalEntityAccounts" lea ON lea."AccountId" = a."Id"
JOIN "ProjectAccounts" pa ON pa."LegalEntityAccountId" = lea."Id" AND pa."IsDisabled" = false
JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id" AND el."IsDisabled" = false
WHERE ac."IsDisabled" = false
AND el."IsComputedInverse" = false
GROUP BY ac."Id", ac."Name"
ORDER BY total_spending DESC
LIMIT 10
            '''.strip(),
            explanation="Groups EXPENSE entries by category (IsComputedInverse=false), ordered by total spending descending."
        ).with_inputs("question", "schema_context", "table_descriptions"),
        
        dspy.Example(
            question="Show me projects that are overspending",
            schema_context="[Schema provided dynamically]",
            table_descriptions="",
            sql_query='''
SELECT 
    p."Brand" as project_name,
    p."TakePlaceDate" as event_date,
    SUM(CASE WHEN el."IsComputedInverse" = false THEN el."Amount" * el."Quantity" ELSE 0 END) as total_expenses,
    SUM(CASE WHEN el."IsComputedInverse" = false AND el."Status" >= 2 THEN el."Amount" * el."Quantity" ELSE 0 END) as committed_expenses,
    ABS(SUM(CASE WHEN el."IsComputedInverse" = true THEN el."Amount" * el."Quantity" ELSE 0 END)) as total_revenue,
    ROUND(
        (SUM(CASE WHEN el."IsComputedInverse" = false THEN el."Amount" * el."Quantity" ELSE 0 END) / 
         NULLIF(ABS(SUM(CASE WHEN el."IsComputedInverse" = true THEN el."Amount" * el."Quantity" ELSE 0 END)), 0) * 100)::numeric, 
        2
    ) as expense_to_revenue_ratio
FROM "Projects" p
JOIN "ProjectAccounts" pa ON pa."ProjectId" = p."Id" AND pa."IsDisabled" = false
JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id" AND el."IsDisabled" = false
WHERE p."IsDisabled" = false
AND p."OriginalProjectId" IS NULL
GROUP BY p."Id", p."Brand", p."TakePlaceDate"
HAVING SUM(CASE WHEN el."IsComputedInverse" = false THEN el."Amount" * el."Quantity" ELSE 0 END) > 
       ABS(SUM(CASE WHEN el."IsComputedInverse" = true THEN el."Amount" * el."Quantity" ELSE 0 END))
ORDER BY expense_to_revenue_ratio DESC
            '''.strip(),
            explanation="Identifies projects where expenses exceed revenue. Uses IsComputedInverse to separate costs from income."
        ).with_inputs("question", "schema_context", "table_descriptions"),
    ]

    def __init__(self):
        """Initialize with few-shot examples."""
        super().__init__()
        self.generate = dspy.ChainOfThought(SQLGeneratorSignature)

    def forward(
        self,
        question: str,
        schema_context: Optional[str] = None,
        table_descriptions: Optional[str] = None,
    ) -> dspy.Prediction:
        """Generate SQL with few-shot context."""
        if not schema_context:
            schema_context = MINIMAL_SCHEMA_CONTEXT
        table_descriptions = table_descriptions or ""
        
        # Generate with examples in context
        return self.generate(
            question=question,
            schema_context=schema_context,
            table_descriptions=table_descriptions,
            demos=self.EXAMPLES,
        )
