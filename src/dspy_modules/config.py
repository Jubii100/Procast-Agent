"""DSPy configuration for Claude LLM."""

from functools import lru_cache
from typing import Optional

import dspy
import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)

# Global LM instance
_configured_lm: Optional[dspy.LM] = None


def configure_claude(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> dspy.LM:
    """
    Configure DSPy with Claude 3.5 Sonnet.
    
    Args:
        api_key: Anthropic API key (uses settings if not provided)
        model: Model identifier (uses settings if not provided)
        max_tokens: Maximum tokens for response (uses settings if not provided)
        temperature: Temperature for sampling (uses settings if not provided)
        
    Returns:
        Configured DSPy LM instance
    """
    global _configured_lm
    
    api_key = api_key or settings.anthropic_api_key
    model = model or settings.llm_model
    max_tokens = max_tokens or settings.llm_max_tokens
    temperature = temperature if temperature is not None else settings.llm_temperature
    
    if not api_key:
        raise ValueError(
            "Anthropic API key not configured. "
            "Set ANTHROPIC_API_KEY environment variable."
        )
    
    logger.info(
        "Configuring Claude LM",
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    
    # Create the LM instance
    claude = dspy.LM(
        f"anthropic/{model}",
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    
    # Configure DSPy globally
    dspy.configure(lm=claude)
    
    _configured_lm = claude
    return claude


def get_configured_lm() -> dspy.LM:
    """
    Get the configured LM instance.
    
    Returns:
        The configured DSPy LM
        
    Raises:
        RuntimeError: If LM not configured
    """
    global _configured_lm
    
    if _configured_lm is None:
        # Auto-configure with defaults
        return configure_claude()
    
    return _configured_lm


def reset_configuration() -> None:
    """Reset the global LM configuration."""
    global _configured_lm
    _configured_lm = None
