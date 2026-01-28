"""Custom evaluation metrics for DSPy modules."""

import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def sql_accuracy_metric(example: Any, prediction: Any, trace: Any = None) -> bool:
    """
    Evaluate SQL generation accuracy.
    
    Checks if the generated SQL is valid and returns reasonable results.
    
    Args:
        example: Expected example with correct output
        prediction: Model prediction
        trace: Optional trace for debugging
        
    Returns:
        True if prediction is acceptable
    """
    # Get the predicted SQL
    pred_sql = getattr(prediction, "sql_query", "").strip()
    
    if not pred_sql:
        return False
    
    # Basic validation checks
    checks = []
    
    # 1. Must be a SELECT statement
    if not pred_sql.upper().startswith("SELECT"):
        checks.append(False)
    else:
        checks.append(True)
    
    # 2. Should not contain dangerous keywords
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
    has_dangerous = any(kw in pred_sql.upper() for kw in dangerous)
    checks.append(not has_dangerous)
    
    # 3. Should reference relevant tables
    relevant_tables = [
        '"Projects"', '"EntryLines"', '"Accounts"', '"AccountCategories"',
        '"Invoices"', '"PurchaseOrders"', '"ProjectAccounts"'
    ]
    has_relevant = any(table in pred_sql for table in relevant_tables)
    checks.append(has_relevant)
    
    # 4. Should filter by IsDisabled (for main tables)
    if any(t in pred_sql for t in ['"Projects"', '"EntryLines"', '"Accounts"']):
        has_disabled_filter = "IsDisabled" in pred_sql or "is_disabled" in pred_sql.lower()
        checks.append(has_disabled_filter)
    else:
        checks.append(True)  # Not applicable
    
    # 5. If we have expected SQL, check for structural similarity
    expected_sql = getattr(example, "sql_query", None)
    if expected_sql:
        # Check if key clauses match
        expected_tables = set(re.findall(r'"(\w+)"', expected_sql))
        pred_tables = set(re.findall(r'"(\w+)"', pred_sql))
        
        # At least 50% table overlap
        if expected_tables:
            overlap = len(expected_tables & pred_tables) / len(expected_tables)
            checks.append(overlap >= 0.5)
        else:
            checks.append(True)
    
    # Pass if all checks pass
    result = all(checks)
    
    if not result:
        logger.debug(
            "SQL accuracy check failed",
            checks=checks,
            sql_preview=pred_sql[:100],
        )
    
    return result


def analysis_quality_metric(example: Any, prediction: Any, trace: Any = None) -> bool:
    """
    Evaluate analysis synthesis quality.
    
    Checks if the analysis is relevant, structured, and actionable.
    
    Args:
        example: Expected example with correct output
        prediction: Model prediction
        trace: Optional trace for debugging
        
    Returns:
        True if prediction is acceptable
    """
    # Get the predicted analysis
    pred_analysis = getattr(prediction, "analysis", "").strip()
    pred_recommendations = getattr(prediction, "recommendations", "").strip()
    pred_confidence = getattr(prediction, "confidence", 0.0)
    
    if not pred_analysis:
        return False
    
    checks = []
    
    # 1. Analysis should have reasonable length (not too short, not too long)
    length = len(pred_analysis)
    checks.append(100 <= length <= 5000)
    
    # 2. Should contain some numbers (budget analysis should have figures)
    has_numbers = bool(re.search(r'\d+', pred_analysis))
    checks.append(has_numbers)
    
    # 3. Should have recommendations
    checks.append(len(pred_recommendations) > 20)
    
    # 4. Confidence should be valid
    try:
        conf = float(pred_confidence)
        checks.append(0.0 <= conf <= 1.0)
    except (ValueError, TypeError):
        checks.append(False)
    
    # 5. Should have some structure (headers, bullet points, or paragraphs)
    has_structure = (
        "##" in pred_analysis or
        "**" in pred_analysis or
        "\n-" in pred_analysis or
        "\n•" in pred_analysis or
        pred_analysis.count("\n\n") >= 2
    )
    checks.append(has_structure)
    
    # 6. Should mention budget-related terms
    budget_terms = ["budget", "spending", "cost", "amount", "total", "expense", "%", "percent"]
    has_budget_terms = any(term in pred_analysis.lower() for term in budget_terms)
    checks.append(has_budget_terms)
    
    # Pass if at least 5 of 6 checks pass
    result = sum(checks) >= 5
    
    if not result:
        logger.debug(
            "Analysis quality check failed",
            checks=checks,
            analysis_preview=pred_analysis[:100],
        )
    
    return result


def confidence_calibration_metric(example: Any, prediction: Any, trace: Any = None) -> bool:
    """
    Check if confidence scores are well-calibrated.
    
    High confidence should match high-quality responses.
    
    Args:
        example: Expected example
        prediction: Model prediction
        trace: Optional trace
        
    Returns:
        True if confidence is calibrated
    """
    pred_confidence = getattr(prediction, "confidence", 0.5)
    pred_analysis = getattr(prediction, "analysis", "")
    
    try:
        conf = float(pred_confidence)
    except (ValueError, TypeError):
        return False
    
    # Simple calibration: long, detailed analyses should have higher confidence
    analysis_length = len(pred_analysis)
    
    if conf > 0.8:
        # High confidence should have substantial analysis
        return analysis_length > 300
    elif conf < 0.5:
        # Low confidence is OK for shorter analyses
        return True
    else:
        # Medium confidence is OK for any reasonable length
        return analysis_length > 100


def combined_metric(example: Any, prediction: Any, trace: Any = None) -> float:
    """
    Combined metric that returns a score instead of boolean.
    
    Useful for more nuanced optimization.
    
    Args:
        example: Expected example
        prediction: Model prediction
        trace: Optional trace
        
    Returns:
        Score from 0.0 to 1.0
    """
    scores = []
    
    # SQL accuracy (if applicable)
    if hasattr(prediction, "sql_query"):
        scores.append(1.0 if sql_accuracy_metric(example, prediction) else 0.0)
    
    # Analysis quality (if applicable)
    if hasattr(prediction, "analysis"):
        scores.append(1.0 if analysis_quality_metric(example, prediction) else 0.0)
    
    # Confidence calibration (if applicable)
    if hasattr(prediction, "confidence"):
        scores.append(1.0 if confidence_calibration_metric(example, prediction) else 0.0)
    
    if not scores:
        return 0.0
    
    return sum(scores) / len(scores)
