"""DSPy compilation pipeline for optimizing modules."""

import json
from pathlib import Path
from typing import Any, Optional

import dspy
import structlog
from dspy.teleprompt import BootstrapFewShot

from src.dspy_modules.config import configure_claude
from src.dspy_modules.sql_generator import SQLGenerator
from src.dspy_modules.analyzer import AnalysisSynthesizer
from src.dspy_modules.metrics import sql_accuracy_metric, analysis_quality_metric

logger = structlog.get_logger(__name__)

# Default paths for compiled modules
COMPILED_MODULES_DIR = Path("compiled_modules")


def load_training_data(path: Path) -> list[dspy.Example]:
    """
    Load training examples from a JSON file.
    
    Args:
        path: Path to JSON file with training examples
        
    Returns:
        List of dspy.Example objects
    """
    with open(path) as f:
        data = json.load(f)
    
    examples = []
    for item in data:
        inputs = item.get("inputs", {})
        outputs = item.get("outputs", {})
        
        example = dspy.Example(**inputs, **outputs)
        example = example.with_inputs(*inputs.keys())
        examples.append(example)
    
    return examples


def compile_sql_generator(
    training_data_path: Optional[Path] = None,
    max_bootstrapped_demos: int = 4,
    save_path: Optional[Path] = None,
) -> SQLGenerator:
    """
    Compile the SQL generator module with optimized prompts.
    
    Args:
        training_data_path: Path to training data JSON
        max_bootstrapped_demos: Maximum number of demonstrations
        save_path: Path to save compiled module
        
    Returns:
        Compiled SQLGenerator module
    """
    logger.info("Compiling SQL Generator")
    
    # Ensure LLM is configured
    configure_claude()
    
    # Load training data or use defaults
    if training_data_path and training_data_path.exists():
        trainset = load_training_data(training_data_path)
        logger.info(f"Loaded {len(trainset)} training examples")
    else:
        # Use built-in examples from the module
        from src.dspy_modules.sql_generator import SQLGeneratorWithExamples
        trainset = SQLGeneratorWithExamples.EXAMPLES
        logger.info("Using built-in training examples")
    
    # Create optimizer
    optimizer = BootstrapFewShot(
        metric=sql_accuracy_metric,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_bootstrapped_demos,
    )
    
    # Compile
    module = SQLGenerator()
    compiled_module = optimizer.compile(module, trainset=trainset)
    
    # Save if path provided
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        compiled_module.save(str(save_path))
        logger.info(f"Saved compiled module to {save_path}")
    
    return compiled_module


def compile_analyzer(
    training_data_path: Optional[Path] = None,
    max_bootstrapped_demos: int = 4,
    save_path: Optional[Path] = None,
) -> AnalysisSynthesizer:
    """
    Compile the analysis synthesizer module.
    
    Args:
        training_data_path: Path to training data JSON
        max_bootstrapped_demos: Maximum number of demonstrations
        save_path: Path to save compiled module
        
    Returns:
        Compiled AnalysisSynthesizer module
    """
    logger.info("Compiling Analysis Synthesizer")
    
    # Ensure LLM is configured
    configure_claude()
    
    # Load training data or use defaults
    if training_data_path and training_data_path.exists():
        trainset = load_training_data(training_data_path)
        logger.info(f"Loaded {len(trainset)} training examples")
    else:
        # Use built-in examples
        from src.dspy_modules.analyzer import AnalysisSynthesizerWithExamples
        trainset = AnalysisSynthesizerWithExamples.EXAMPLES
        logger.info("Using built-in training examples")
    
    # Create optimizer
    optimizer = BootstrapFewShot(
        metric=analysis_quality_metric,
        max_bootstrapped_demos=max_bootstrapped_demos,
        max_labeled_demos=max_bootstrapped_demos,
    )
    
    # Compile
    module = AnalysisSynthesizer()
    compiled_module = optimizer.compile(module, trainset=trainset)
    
    # Save if path provided
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        compiled_module.save(str(save_path))
        logger.info(f"Saved compiled module to {save_path}")
    
    return compiled_module


def load_compiled_module(path: Path, module_class: type) -> Any:
    """
    Load a previously compiled module.
    
    Args:
        path: Path to saved module
        module_class: The module class to instantiate
        
    Returns:
        Loaded module instance
    """
    module = module_class()
    module.load(str(path))
    logger.info(f"Loaded compiled module from {path}")
    return module


def compile_all_modules(
    sql_training_path: Optional[Path] = None,
    analysis_training_path: Optional[Path] = None,
    output_dir: Path = COMPILED_MODULES_DIR,
) -> dict[str, Any]:
    """
    Compile all DSPy modules.
    
    Args:
        sql_training_path: Path to SQL training data
        analysis_training_path: Path to analysis training data
        output_dir: Directory to save compiled modules
        
    Returns:
        Dictionary of compiled modules
    """
    logger.info("Compiling all modules")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    compiled = {}
    
    # Compile SQL Generator
    compiled["sql_generator"] = compile_sql_generator(
        training_data_path=sql_training_path,
        save_path=output_dir / "sql_generator.json",
    )
    
    # Compile Analyzer
    compiled["analyzer"] = compile_analyzer(
        training_data_path=analysis_training_path,
        save_path=output_dir / "analyzer.json",
    )
    
    logger.info("All modules compiled successfully")
    return compiled


if __name__ == "__main__":
    # CLI for compiling modules
    import argparse
    
    parser = argparse.ArgumentParser(description="Compile DSPy modules")
    parser.add_argument(
        "--sql-training",
        type=Path,
        help="Path to SQL training data JSON",
    )
    parser.add_argument(
        "--analysis-training",
        type=Path,
        help="Path to analysis training data JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=COMPILED_MODULES_DIR,
        help="Output directory for compiled modules",
    )
    
    args = parser.parse_args()
    
    compile_all_modules(
        sql_training_path=args.sql_training,
        analysis_training_path=args.analysis_training,
        output_dir=args.output_dir,
    )
