"""Analysis Synthesizer DSPy module for Procast AI."""

import json
from typing import Any, Optional, Union

import dspy
import structlog

from src.dspy_modules.signatures import (
    AnalysisSynthesizerSignature,
    SummarizationSignature,
)

logger = structlog.get_logger(__name__)


# Budget analysis context - provides guidance for interpreting results
BUDGET_ANALYSIS_CONTEXT = """
Budget Analysis Guidelines:
1. Overspending: When committed > budgeted, flag as critical
2. At-Risk: When spending is >80% of budget, flag as warning
3. Variance: Calculate percentage difference from budget
4. Trends: Compare current vs historical patterns
5. Categories: Identify top spending categories

Key Metrics to Highlight:
- Total budget vs actual spending
- Percentage utilized
- Top expense categories
- Month-over-month changes
- Currency-adjusted comparisons

Red Flags to Watch:
- Spending velocity exceeding plan
- Unusual spikes in specific categories
- Projects approaching or exceeding budget
- Uncommitted large expenses near event date
"""


class AnalysisSynthesizer(dspy.Module):
    """
    Synthesizes financial analysis from database query results.
    
    This module interprets query results and provides actionable
    insights, recommendations, and confidence scores.
    """

    def __init__(self):
        """Initialize the analysis synthesizer."""
        super().__init__()
        
        # Main analysis with Chain-of-Thought
        self.synthesize = dspy.ChainOfThought(AnalysisSynthesizerSignature)
        
        # Summarization for different audience levels
        self.summarize = dspy.ChainOfThought(SummarizationSignature)

    def forward(
        self,
        question: str,
        query_results: Union[list[dict[str, Any]], str],
        budget_context: Optional[str] = None,
    ) -> dspy.Prediction:
        """
        Synthesize analysis from query results.
        
        Args:
            question: The original user question
            query_results: Data from database query (list or JSON string)
            budget_context: Additional budget context (uses default if not provided)
            
        Returns:
            Prediction with analysis, recommendations, and confidence
        """
        # Convert results to string if needed
        if isinstance(query_results, list):
            # Limit data size for context window
            if len(query_results) > 50:
                logger.info(
                    "Truncating results for analysis",
                    original_count=len(query_results),
                    truncated_to=50,
                )
                query_results = query_results[:50]
            query_results = json.dumps(query_results, default=str, indent=2)
        
        budget_context = budget_context or BUDGET_ANALYSIS_CONTEXT
        
        logger.info(
            "Synthesizing analysis",
            question=question[:100],
            results_length=len(query_results),
        )
        
        result = self.synthesize(
            question=question,
            query_results=query_results,
            budget_context=budget_context,
        )
        
        # Ensure confidence is a float
        confidence = result.confidence
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = 0.7  # Default if parsing fails
        
        # Clamp confidence to valid range
        confidence = max(0.0, min(1.0, confidence))
        
        logger.debug(
            "Analysis synthesized",
            confidence=confidence,
            analysis_length=len(result.analysis) if result.analysis else 0,
        )
        
        return dspy.Prediction(
            analysis=result.analysis,
            recommendations=result.recommendations,
            confidence=confidence,
        )

    def forward_with_summary(
        self,
        question: str,
        query_results: Union[list[dict[str, Any]], str],
        expertise_level: str = "business",
        budget_context: Optional[str] = None,
    ) -> dspy.Prediction:
        """
        Synthesize analysis with a summarized version for different audiences.
        
        Args:
            question: The original user question
            query_results: Data from database query
            expertise_level: One of 'technical', 'business', 'executive'
            budget_context: Additional budget context
            
        Returns:
            Prediction with analysis, recommendations, confidence, summary, and key_metrics
        """
        # First, get the detailed analysis
        detailed = self.forward(
            question=question,
            query_results=query_results,
            budget_context=budget_context,
        )
        
        # Then summarize for the target audience
        summary_result = self.summarize(
            detailed_analysis=detailed.analysis,
            user_expertise_level=expertise_level,
        )
        
        return dspy.Prediction(
            analysis=detailed.analysis,
            recommendations=detailed.recommendations,
            confidence=detailed.confidence,
            summary=summary_result.summary,
            key_metrics=summary_result.key_metrics,
        )


class AnalysisSynthesizerWithExamples(dspy.Module):
    """
    Analysis Synthesizer with few-shot examples for consistent output format.
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
- **Status**: ⚠️ AT RISK - Approaching budget ceiling

### Conference Q2
- **Budgeted**: $200,000
- **Committed**: $180,000
- **Utilization**: 90%
- **Status**: ⚠️ AT RISK - Very close to budget limit

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
