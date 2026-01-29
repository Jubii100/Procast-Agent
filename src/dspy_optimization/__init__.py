"""DSPy optimization module for prompt compilation and training.

This package contains DSPy-specific optimization utilities that are separate
from the runtime agent code. It includes:

- *WithExamples classes for few-shot prompt optimization
- DSPy compilation pipeline (BootstrapFewShot)
- Training data (JSON examples for SQL and analysis)

This module is NOT used during runtime agent execution. It is only used
for offline prompt optimization and DSPy compilation.
"""

from src.dspy_optimization.with_examples import (
    IntentClassifierWithExamples,
    SQLGeneratorWithExamples,
    AnalysisSynthesizerWithExamples,
)

__all__ = [
    "IntentClassifierWithExamples",
    "SQLGeneratorWithExamples",
    "AnalysisSynthesizerWithExamples",
]
