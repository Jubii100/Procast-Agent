"""Intent Classifier DSPy module for Procast AI."""

from typing import Optional

import dspy
import structlog

from src.dspy_modules.signatures import IntentClassifierSignature
from src.dspy_modules.config import get_auxiliary_lm

logger = structlog.get_logger(__name__)


class IntentClassifier(dspy.Module):
    """
    Classifies user intent for routing to appropriate handlers.
    
    Determines whether a question needs database access, requires
    clarification, can be answered with general information, or is
    a friendly conversational message (greeting/small talk).
    """

    # Valid intents
    VALID_INTENTS = {"db_query", "clarify", "general_info", "friendly_chat"}

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
        
        Uses a cheaper auxiliary LLM model (configured via settings.llm_auxiliary_model)
        to reduce costs for the intent classification step.
        
        Args:
            question: The user's question
            conversation_history: Previous conversation for context
            
        Returns:
            Prediction with intent, requires_db_query, clarification_needed, clarification_questions
        """
        conversation_history = conversation_history or ""
        
        logger.info("Classifying intent", question=question[:100])
        
        # Use the cheaper auxiliary LM for this call
        auxiliary_lm = get_auxiliary_lm()
        with dspy.context(lm=auxiliary_lm):
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
