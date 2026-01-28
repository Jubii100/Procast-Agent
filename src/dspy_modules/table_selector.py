"""DSPy module for intelligent table/domain selection.

This module determines which database domains are relevant for a user's question,
enabling cost-efficient schema loading by only including relevant table descriptions.
"""

from typing import Optional

import dspy
import structlog

from src.db.schema_registry import (
    DATABASE_SUMMARY,
    get_all_domains,
    DOMAIN_TABLES,
)

logger = structlog.get_logger(__name__)


class TableSelectorSignature(dspy.Signature):
    """Select relevant database domains for a natural language question.
    
    Given a user question about budget/financial data and a summary of available
    database domains, identify which domains contain the tables needed to answer
    the question. Be selective - only include domains that are truly necessary.
    """
    
    question: str = dspy.InputField(
        desc="The user's natural language question about budget data"
    )
    db_summary: str = dspy.InputField(
        desc="Summary of the database structure and available domains"
    )
    available_domains: str = dspy.InputField(
        desc="List of available domains with their tables"
    )
    
    selected_domains: str = dspy.OutputField(
        desc="Comma-separated list of domain names needed to answer the question. "
             "Select ONLY necessary domains to minimize context size. "
             "Common selections: 'projects,budgets' for budget queries, "
             "'projects,budgets,accounts' for category analysis, "
             "'projects,budgets,actuals' for spending vs budget comparisons."
    )
    reasoning: str = dspy.OutputField(
        desc="Brief explanation of why these domains were selected"
    )


# Domain descriptions for the selector
DOMAIN_DESCRIPTIONS = """
AVAILABLE DOMAINS:

1. projects - Project/event management (Projects, SubProjects, ProjectAccounts, team membership)
   USE FOR: Questions about specific projects, events, project budgets, team members

2. budgets - Budget line items and history (EntryLines, SubAccounts, EntryLine_H)
   USE FOR: Budget totals, line items, spending amounts, budget changes, trends

3. accounts - Account categories and hierarchy (Accounts, AccountCategories, LegalEntityAccounts)
   USE FOR: Expense categories, account breakdowns, category analysis

4. actuals - Invoices and purchase orders (Invoices, PurchaseOrders, Reconciliations)
   USE FOR: Actual spending, invoices, POs, budget vs actuals comparisons

5. users - People and companies (People, AspNetUsers, Companies)
   USE FOR: User information, who made changes, company details

6. currency - Currency and FX rates (Currencies, CurrencyTuples, ConstantFxRates)
   USE FOR: Multi-currency analysis, currency conversions, FX rates

7. reference - Reference data (Countries, Regions, Industries, CostCodes)
   USE FOR: Location-based analysis, industry breakdown, cost center analysis

8. workspaces - Workspace organization (PersonalWorkspaces, SharedWorkspaces, Folders)
   USE FOR: Workspace structure (rarely needed for budget analysis)

9. approvals - Approval workflows (Approvals, ReviewRequests)
   USE FOR: Approval status, pending reviews (rarely needed)

COMMON COMBINATIONS:
- Budget overview: projects, budgets
- Category breakdown: projects, budgets, accounts
- Spending analysis: projects, budgets, actuals
- Overspending detection: projects, budgets
- Trend analysis: projects, budgets (uses EntryLine_H)
- Multi-currency: projects, budgets, currency
"""


class TableSelector(dspy.Module):
    """
    Selects relevant database domains for a user question.
    
    Uses a lightweight LLM call to determine which domains are needed,
    enabling cost-efficient schema loading.
    """
    
    # Minimum domains always included for basic budget queries
    BASE_DOMAINS = {"projects", "budgets"}
    
    # All valid domain names
    VALID_DOMAINS = set(get_all_domains())

    def __init__(self):
        """Initialize the table selector."""
        super().__init__()
        self.select = dspy.Predict(TableSelectorSignature)

    def forward(
        self,
        question: str,
        db_summary: Optional[str] = None,
    ) -> dspy.Prediction:
        """
        Select relevant domains for the question.
        
        Args:
            question: User's natural language question
            db_summary: Optional custom database summary
            
        Returns:
            Prediction with selected_domains and reasoning
        """
        db_summary = db_summary or DATABASE_SUMMARY
        
        logger.debug("Selecting domains for question", question=question[:100])
        
        result = self.select(
            question=question,
            db_summary=db_summary,
            available_domains=DOMAIN_DESCRIPTIONS,
        )
        
        # Parse and validate selected domains
        selected = self._parse_domains(result.selected_domains)
        
        # Ensure base domains are always included
        selected = selected.union(self.BASE_DOMAINS)
        
        logger.info(
            "Domains selected",
            domains=list(selected),
            reasoning=result.reasoning[:100] if result.reasoning else None,
        )
        
        return dspy.Prediction(
            selected_domains=list(selected),
            reasoning=result.reasoning,
        )

    def _parse_domains(self, domains_str: str) -> set[str]:
        """Parse and validate domain string."""
        if not domains_str:
            return set()
        
        # Parse comma-separated list
        domains = set()
        for part in domains_str.lower().replace(" ", "").split(","):
            part = part.strip()
            if part in self.VALID_DOMAINS:
                domains.add(part)
        
        return domains


class TableSelectorWithRules(dspy.Module):
    """
    Rule-enhanced table selector for faster, cheaper domain selection.
    
    Uses keyword matching as a first pass, with LLM fallback for ambiguous cases.
    This reduces LLM calls for common query patterns.
    """
    
    # Keyword-based domain mapping for common patterns
    KEYWORD_RULES = {
        "budgets": ["budget", "spending", "cost", "amount", "expense", "entry", "line item",
                   "total", "sum", "committed", "allocated"],
        "projects": ["project", "event", "brand", "edition", "subproject"],
        "accounts": ["category", "account", "breakdown", "categorize", "expense type"],
        "actuals": ["invoice", "purchase order", "po", "actual", "posted", "reconcil"],
        "users": ["user", "person", "who", "team", "member", "owner", "created by"],
        "currency": ["currency", "fx", "exchange", "rate", "convert", "usd", "eur"],
        "reference": ["country", "region", "industry", "division", "cost code"],
    }
    
    BASE_DOMAINS = {"projects", "budgets"}
    VALID_DOMAINS = set(get_all_domains())

    def __init__(self, use_llm_fallback: bool = True):
        """
        Initialize the rule-based selector.
        
        Args:
            use_llm_fallback: Whether to use LLM for ambiguous cases
        """
        super().__init__()
        self.use_llm_fallback = use_llm_fallback
        if use_llm_fallback:
            self.llm_selector = TableSelector()

    def forward(
        self,
        question: str,
        db_summary: Optional[str] = None,
    ) -> dspy.Prediction:
        """
        Select relevant domains using rules first, LLM fallback if needed.
        
        Args:
            question: User's natural language question
            db_summary: Optional database summary (for LLM fallback)
            
        Returns:
            Prediction with selected_domains and reasoning
        """
        question_lower = question.lower()
        
        # Apply keyword rules
        matched_domains = set()
        matched_keywords = []
        
        for domain, keywords in self.KEYWORD_RULES.items():
            for keyword in keywords:
                if keyword in question_lower:
                    matched_domains.add(domain)
                    matched_keywords.append(f"{keyword}→{domain}")
                    break  # One match per domain is enough
        
        # Always include base domains
        matched_domains = matched_domains.union(self.BASE_DOMAINS)
        
        # If we found specific domains via rules, use them
        if len(matched_domains) > len(self.BASE_DOMAINS):
            reasoning = f"Rule-based selection: {', '.join(matched_keywords)}"
            logger.info(
                "Domains selected via rules",
                domains=list(matched_domains),
            )
            return dspy.Prediction(
                selected_domains=list(matched_domains),
                reasoning=reasoning,
            )
        
        # Fallback to LLM for ambiguous questions
        if self.use_llm_fallback:
            logger.debug("Using LLM fallback for domain selection")
            return self.llm_selector(question=question, db_summary=db_summary)
        
        # Default to base domains
        return dspy.Prediction(
            selected_domains=list(self.BASE_DOMAINS),
            reasoning="Default selection: base domains only",
        )


def select_domains_for_question(
    question: str,
    use_rules_first: bool = True,
) -> list[str]:
    """
    Convenience function to select domains for a question.
    
    Args:
        question: User's natural language question
        use_rules_first: Try rule-based selection before LLM
        
    Returns:
        List of selected domain names
    """
    if use_rules_first:
        selector = TableSelectorWithRules(use_llm_fallback=True)
    else:
        selector = TableSelector()
    
    result = selector(question=question)
    return result.selected_domains
