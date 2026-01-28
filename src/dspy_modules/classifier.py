"""Intent Classifier DSPy module for Procast AI."""

from typing import Optional

import dspy
import structlog

from src.dspy_modules.signatures import IntentClassifierSignature

logger = structlog.get_logger(__name__)


class IntentClassifier(dspy.Module):
    """
    Classifies user intent for routing to appropriate handlers.
    
    Determines whether a question needs database access, requires
    clarification, or can be answered with general information.
    """

    # Valid intents
    VALID_INTENTS = {"db_query", "clarify", "general_info"}

    def __init__(self):
        """Initialize the intent classifier."""
        super().__init__()
        
        # Use Predict for simpler classification task
        self.classify = dspy.Predict(IntentClassifierSignature)

    def forward(
        self,
        question: str,
        conversation_history: Optional[str] = None,
    ) -> dspy.Prediction:
        """
        Classify user intent.
        
        Args:
            question: The user's question
            conversation_history: Previous conversation for context
            
        Returns:
            Prediction with intent, requires_db_query, clarification_needed, clarification_questions
        """
        conversation_history = conversation_history or ""
        
        logger.info("Classifying intent", question=question[:100])
        
        result = self.classify(
            question=question,
            conversation_history=conversation_history,
        )
        
        # Normalize intent
        intent = result.intent.lower().strip()
        if intent not in self.VALID_INTENTS:
            # Default to db_query for budget-related questions
            intent = "db_query"
        
        # Parse boolean fields
        requires_db = self._parse_bool(result.requires_db_query)
        needs_clarification = self._parse_bool(result.clarification_needed)
        
        # If clarification needed, ensure intent matches
        if needs_clarification:
            intent = "clarify"
        
        logger.debug(
            "Intent classified",
            intent=intent,
            requires_db=requires_db,
            needs_clarification=needs_clarification,
        )
        
        return dspy.Prediction(
            intent=intent,
            requires_db_query=requires_db,
            clarification_needed=needs_clarification,
            clarification_questions=result.clarification_questions if needs_clarification else "",
        )

    @staticmethod
    def _parse_bool(value) -> bool:
        """Parse a value to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1")
        return bool(value)


class IntentClassifierWithExamples(dspy.Module):
    """
    Intent Classifier with few-shot examples for better accuracy.
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
