"""Tests for DSPy modules."""

import pytest

from src.dspy_modules.table_selector import (
    TableSelector,
    TableSelectorWithRules,
    select_domains_for_question,
    DOMAIN_DESCRIPTIONS,
)
from src.db.schema_registry import get_all_domains


class TestTableSelectorWithRules:
    """Tests for the rule-based table selector."""
    
    def test_budget_keywords(self):
        """Test budget-related keywords are detected."""
        selector = TableSelectorWithRules(use_llm_fallback=False)
        
        result = selector(question="What is the total budget for project X?")
        
        assert "budgets" in result.selected_domains
        assert "projects" in result.selected_domains
    
    def test_category_keywords(self):
        """Test category keywords trigger accounts domain."""
        selector = TableSelectorWithRules(use_llm_fallback=False)
        
        result = selector(question="Show me spending breakdown by category")
        
        assert "accounts" in result.selected_domains
    
    def test_invoice_keywords(self):
        """Test invoice keywords trigger actuals domain."""
        selector = TableSelectorWithRules(use_llm_fallback=False)
        
        result = selector(question="Show me all invoices for this project")
        
        assert "actuals" in result.selected_domains
    
    def test_user_keywords(self):
        """Test user keywords trigger users domain."""
        selector = TableSelectorWithRules(use_llm_fallback=False)
        
        result = selector(question="Who created this budget entry?")
        
        assert "users" in result.selected_domains
    
    def test_currency_keywords(self):
        """Test currency keywords trigger currency domain."""
        selector = TableSelectorWithRules(use_llm_fallback=False)
        
        result = selector(question="Convert budget to USD")
        
        assert "currency" in result.selected_domains
    
    def test_base_domains_always_included(self):
        """Test base domains are always included."""
        selector = TableSelectorWithRules(use_llm_fallback=False)
        
        # Even an ambiguous question should include base domains
        result = selector(question="Tell me something")
        
        assert "projects" in result.selected_domains
        assert "budgets" in result.selected_domains
    
    def test_reasoning_includes_rule_info(self):
        """Test reasoning mentions rule-based selection when matching non-base domains."""
        selector = TableSelectorWithRules(use_llm_fallback=False)
        
        # Use a question that matches a domain outside BASE_DOMAINS (actuals via "invoice")
        result = selector(question="Show me all invoices")
        
        assert "Rule-based" in result.reasoning
        assert "actuals" in result.selected_domains


class TestTableSelectorHelpers:
    """Tests for table selector helper functions."""
    
    def test_domain_descriptions_complete(self):
        """Test domain descriptions cover all domains."""
        all_domains = get_all_domains()
        
        for domain in all_domains:
            # Each domain should be mentioned in descriptions
            assert domain in DOMAIN_DESCRIPTIONS.lower(), f"Domain {domain} not in descriptions"
    
    def test_select_domains_convenience_function(self):
        """Test that TableSelectorWithRules can select domains."""
        # Use direct instantiation without LLM fallback for testing
        selector = TableSelectorWithRules(use_llm_fallback=False)
        result = selector(question="Show me invoice category breakdown")
        
        assert isinstance(result.selected_domains, list)
        assert len(result.selected_domains) >= 2  # At least base domains
        assert "actuals" in result.selected_domains  # invoice keyword
        assert "accounts" in result.selected_domains  # category keyword (singular)


class TestSQLGeneratorSignatures:
    """Tests for SQL generator signatures."""
    
    def test_signatures_exist(self):
        """Test that required signatures are defined and are DSPy Signature classes."""
        import dspy
        from src.dspy_modules.signatures import (
            SQLGeneratorSignature,
            AnalysisSynthesizerSignature,
            IntentClassifierSignature,
        )
        
        # Check signatures are subclasses of dspy.Signature
        assert issubclass(SQLGeneratorSignature, dspy.Signature)
        assert issubclass(AnalysisSynthesizerSignature, dspy.Signature)
        assert issubclass(IntentClassifierSignature, dspy.Signature)


class TestAnalyzerModule:
    """Tests for the analyzer module structure."""
    
    def test_analyzer_can_instantiate(self):
        """Test analyzer can be instantiated."""
        from src.dspy_modules.analyzer import AnalysisSynthesizer
        
        # Should not raise
        analyzer = AnalysisSynthesizer()
        assert analyzer is not None


class TestClassifierModule:
    """Tests for the classifier module structure."""
    
    def test_classifier_can_instantiate(self):
        """Test classifier can be instantiated."""
        from src.dspy_modules.classifier import IntentClassifier
        
        classifier = IntentClassifier()
        assert classifier is not None


class TestSQLGeneratorModule:
    """Tests for the SQL generator module structure."""
    
    def test_generator_can_instantiate(self):
        """Test SQL generator can be instantiated."""
        from src.dspy_modules.sql_generator import SQLGenerator
        
        generator = SQLGenerator()
        assert generator is not None
