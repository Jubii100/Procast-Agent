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
