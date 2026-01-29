"""DSPy configuration for Claude LLM."""

from functools import lru_cache
from typing import Any, Optional

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
        cache_enabled=settings.llm_cache_enabled,
    )
    
    # Create the LM instance
    claude = dspy.LM(
        f"anthropic/{model}",
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=temperature,
        cache=settings.llm_cache_enabled,
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


# Auxiliary LM (cheaper model for domain selection, intent classification, etc.)
_auxiliary_lm: Optional[dspy.LM] = None


def get_auxiliary_lm() -> dspy.LM:
    """
    Get a lightweight LM for auxiliary tasks.
    
    Uses a cheaper model (claude-3-5-haiku by default) to reduce costs
    for tasks like domain selection and intent classification.
    Does NOT override the global LM used for SQL generation.
    
    Returns:
        DSPy LM instance configured for auxiliary tasks
    """
    global _auxiliary_lm
    
    if _auxiliary_lm is not None:
        return _auxiliary_lm
    
    api_key = settings.anthropic_api_key
    model = settings.llm_auxiliary_model
    
    if not api_key:
        raise ValueError(
            "Anthropic API key not configured. "
            "Set ANTHROPIC_API_KEY environment variable."
        )
    
    logger.info(
        "Configuring auxiliary LM (cheap model)",
        model=model,
        cache_enabled=settings.llm_cache_enabled,
    )
    
    _auxiliary_lm = dspy.LM(
        f"anthropic/{model}",
        api_key=api_key,
        max_tokens=1024,  # Auxiliary task output is small
        temperature=0.0,
        cache=settings.llm_cache_enabled,
    )
    
    return _auxiliary_lm


def set_lm_cache_enabled(enabled: bool, initialize: bool = False) -> dict[str, bool]:
    """Set LM cache flags and return previous values."""
    previous: dict[str, bool] = {}
    if initialize and _configured_lm is None:
        configure_claude()
    if initialize and _auxiliary_lm is None:
        get_auxiliary_lm()

    if _configured_lm is not None:
        previous["primary"] = _configured_lm.cache
        _configured_lm.cache = enabled
    if _auxiliary_lm is not None:
        previous["auxiliary"] = _auxiliary_lm.cache
        _auxiliary_lm.cache = enabled
    return previous


def restore_lm_cache_state(previous: dict[str, bool]) -> None:
    """Restore LM cache flags from a previous snapshot."""
    if _configured_lm is not None and "primary" in previous:
        _configured_lm.cache = previous["primary"]
    if _auxiliary_lm is not None and "auxiliary" in previous:
        _auxiliary_lm.cache = previous["auxiliary"]


def get_lm_usage_snapshot() -> dict[str, int]:
    """Capture current LM history lengths for usage deltas."""
    snapshot: dict[str, int] = {}
    if _configured_lm is not None:
        snapshot["primary"] = len(_configured_lm.history)
    if _auxiliary_lm is not None:
        snapshot["auxiliary"] = len(_auxiliary_lm.history)
    return snapshot


def get_lm_usage_entries(snapshot: dict[str, int]) -> list[dict[str, Any]]:
    """Return LM history entries since the provided snapshot."""
    entries: list[dict[str, Any]] = []
    if _configured_lm is not None:
        entries.extend(_collect_usage_entries(_configured_lm, snapshot.get("primary", 0), "primary"))
    if _auxiliary_lm is not None:
        entries.extend(_collect_usage_entries(_auxiliary_lm, snapshot.get("auxiliary", 0), "auxiliary"))
    return entries


def _collect_usage_entries(lm: dspy.LM, start_index: int, label: str) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for entry in lm.history[start_index:]:
        response = entry.get("response")
        collected.append(
            {
                "lm_label": label,
                "model": entry.get("model"),
                "usage": entry.get("usage") or {},
                "cost": entry.get("cost"),
                "cache_hit": getattr(response, "cache_hit", None),
                "timestamp": entry.get("timestamp"),
                "uuid": entry.get("uuid"),
            }
        )
    return collected
