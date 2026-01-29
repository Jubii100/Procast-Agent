"""DSPy modules with few-shot examples for optimization/compilation.

This module contains *WithExamples variants of DSPy modules used for:
- DSPy BootstrapFewShot prompt optimization
- Offline compilation and training

These classes are NOT used during runtime agent execution.
"""

import json
from typing import Any, Optional, Union

import dspy

from src.dspy_modules.signatures import (
    IntentClassifierSignature,
    SQLGeneratorSignature,
    AnalysisSynthesizerSignature,
)

# Import BUDGET_ANALYSIS_CONTEXT for AnalysisSynthesizerWithExamples
from src.dspy_modules.analyzer import BUDGET_ANALYSIS_CONTEXT

# Import MINIMAL_SCHEMA_CONTEXT for SQLGeneratorWithExamples
from src.dspy_modules.sql_generator import MINIMAL_SCHEMA_CONTEXT


# =============================================================================
# IntentClassifierWithExamples
# =============================================================================

class IntentClassifierWithExamples(dspy.Module):
    """
    Intent Classifier with few-shot examples for better accuracy.
    
    Used for DSPy compilation/optimization, not for runtime execution.
    """

    EXAMPLES = [
        # Database query examples
        dspy.Example(
            question="What is our total budget for Q1 events?",
            conversation_history="",
            intent="db_query",
            requires_db_query=True,
            clarification_needed=False,
            clarification_questions="",
        ).with_inputs("question", "conversation_history"),
        
        dspy.Example(
            question="Show me projects that are over budget",
            conversation_history="",
            intent="db_query",
            requires_db_query=True,
            clarification_needed=False,
            clarification_questions="",
        ).with_inputs("question", "conversation_history"),
        
        dspy.Example(
            question="Which category has the highest spending?",
            conversation_history="",
            intent="db_query",
            requires_db_query=True,
            clarification_needed=False,
            clarification_questions="",
        ).with_inputs("question", "conversation_history"),
        
        # Clarification needed examples
        dspy.Example(
            question="Tell me about the project",
            conversation_history="",
            intent="clarify",
            requires_db_query=False,
            clarification_needed=True,
            clarification_questions="Which project would you like to know about? Please provide a project name or ID.",
        ).with_inputs("question", "conversation_history"),
        
        dspy.Example(
            question="Is this good?",
            conversation_history="I just reviewed the Summit 2026 budget.",
            intent="clarify",
            requires_db_query=False,
            clarification_needed=True,
            clarification_questions="Could you clarify what aspect you'd like me to evaluate? For example: budget utilization, spending trends, or cost allocation?",
        ).with_inputs("question", "conversation_history"),
        
        # General info examples
        dspy.Example(
            question="What types of expense categories does Procast support?",
            conversation_history="",
            intent="general_info",
            requires_db_query=False,
            clarification_needed=False,
            clarification_questions="",
        ).with_inputs("question", "conversation_history"),
        
        dspy.Example(
            question="How do I interpret the status codes?",
            conversation_history="",
            intent="general_info",
            requires_db_query=False,
            clarification_needed=False,
            clarification_questions="",
        ).with_inputs("question", "conversation_history"),
    ]

    def __init__(self):
        """Initialize with examples."""
        super().__init__()
        self.classify = dspy.Predict(IntentClassifierSignature)

    def forward(
        self,
        question: str,
        conversation_history: Optional[str] = None,
    ) -> dspy.Prediction:
        """Classify intent with few-shot context."""
        conversation_history = conversation_history or ""
        
        result = self.classify(
            question=question,
            conversation_history=conversation_history,
            demos=self.EXAMPLES,
        )
        
        # Normalize and validate intent
        intent = result.intent.lower().strip()
        valid_intents = {"db_query", "clarify", "general_info"}
        if intent not in valid_intents:
            intent = "db_query"
        
        # Parse booleans
        requires_db = result.requires_db_query
        if isinstance(requires_db, str):
            requires_db = requires_db.lower() in ("true", "yes", "1")
        
        needs_clarification = result.clarification_needed
        if isinstance(needs_clarification, str):
            needs_clarification = needs_clarification.lower() in ("true", "yes", "1")
        
        return dspy.Prediction(
            intent=intent,
            requires_db_query=bool(requires_db),
            clarification_needed=bool(needs_clarification),
            clarification_questions=result.clarification_questions if needs_clarification else "",
        )


# =============================================================================
# SQLGeneratorWithExamples
# =============================================================================

class SQLGeneratorWithExamples(dspy.Module):
    """
    SQL Generator with few-shot examples for better accuracy.
    
    This variant includes demonstrations of good SQL queries
    for common budget analysis patterns.
    
    Used for DSPy compilation/optimization, not for runtime execution.
    """

    # Few-shot examples for budget analysis
    # MUST: 1) Filter by IsComputedInverse for revenue/expenses
    #       2) Filter by OriginalProjectId IS NULL to exclude scenarios
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
            explanation="Sums EXPENSE entry lines across original projects only. Excludes: revenue (IsComputedInverse=true), scenarios (OriginalProjectId not null), disabled records."
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
            explanation="Comprehensive overview of original projects only. Separates expenses (IsComputedInverse=false) from revenue (IsComputedInverse=true). Excludes scenario copies."
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
JOIN "Projects" p ON p."Id" = pa."ProjectId" AND p."IsDisabled" = false AND p."OriginalProjectId" IS NULL
JOIN "EntryLines" el ON el."ProjectAccountId" = pa."Id" AND el."IsDisabled" = false
WHERE ac."IsDisabled" = false
AND el."IsComputedInverse" = false
GROUP BY ac."Id", ac."Name"
ORDER BY total_spending DESC
LIMIT 10
            '''.strip(),
            explanation="Groups EXPENSE entries by category for original projects only. Excludes revenue entries and scenario copies."
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
            explanation="Identifies original projects where expenses exceed revenue. Excludes scenario copies using OriginalProjectId IS NULL."
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


# =============================================================================
# AnalysisSynthesizerWithExamples
# =============================================================================

class AnalysisSynthesizerWithExamples(dspy.Module):
    """
    Analysis Synthesizer with few-shot examples for consistent output format.
    
    Used for DSPy compilation/optimization, not for runtime execution.
    """

    EXAMPLES = [
        dspy.Example(
            question="What is our budget status?",
            query_results=json.dumps([
                {"project_name": "Summit 2026", "budgeted": 500000, "committed": 425000, "percentage_used": 85},
                {"project_name": "Conference Q2", "budgeted": 200000, "committed": 180000, "percentage_used": 90},
            ]),
            budget_context=BUDGET_ANALYSIS_CONTEXT,
            analysis="""
## Budget Status Overview

Based on the current data, here's the budget status across projects:

### Summit 2026
- **Budgeted**: $500,000
- **Committed**: $425,000
- **Utilization**: 85%
- **Status**: AT RISK - Approaching budget ceiling

### Conference Q2
- **Budgeted**: $200,000
- **Committed**: $180,000
- **Utilization**: 90%
- **Status**: AT RISK - Very close to budget limit

Both projects are in the "at-risk" zone with utilization above 80%. Immediate attention is recommended to prevent overspending.
            """.strip(),
            recommendations="""
1. **Review Summit 2026 uncommitted items** - With 15% remaining, prioritize essential expenses only
2. **Conference Q2 spending freeze** - Consider a soft spending freeze until final costs are confirmed
3. **Identify potential savings** - Review line items for opportunities to reduce committed costs
4. **Prepare variance reports** - Document any potential overruns for stakeholder communication
            """.strip(),
            confidence=0.92,
        ).with_inputs("question", "query_results", "budget_context"),
    ]

    def __init__(self):
        """Initialize with examples."""
        super().__init__()
        self.synthesize = dspy.ChainOfThought(AnalysisSynthesizerSignature)

    def forward(
        self,
        question: str,
        query_results: Union[list[dict[str, Any]], str],
        budget_context: Optional[str] = None,
    ) -> dspy.Prediction:
        """Generate analysis with few-shot context."""
        if isinstance(query_results, list):
            if len(query_results) > 50:
                query_results = query_results[:50]
            query_results = json.dumps(query_results, default=str, indent=2)
        
        budget_context = budget_context or BUDGET_ANALYSIS_CONTEXT
        
        return self.synthesize(
            question=question,
            query_results=query_results,
            budget_context=budget_context,
            demos=self.EXAMPLES,
        )
