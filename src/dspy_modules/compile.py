"""DEPRECATED: DSPy compilation has moved to src.dspy_optimization.compile.

This module is kept for backward compatibility. Use the new location:
    python -m src.dspy_optimization.compile

All compilation functionality is now in src/dspy_optimization/.
"""

# Re-export everything from the new location for backward compatibility
from src.dspy_optimization.compile import (
    load_training_data,
    compile_sql_generator,
    compile_analyzer,
    load_compiled_module,
    compile_all_modules,
    COMPILED_MODULES_DIR,
)

__all__ = [
    "load_training_data",
    "compile_sql_generator",
    "compile_analyzer",
    "load_compiled_module",
    "compile_all_modules",
    "COMPILED_MODULES_DIR",
]


if __name__ == "__main__":
    import sys
    print("DEPRECATED: Please use 'python -m src.dspy_optimization.compile' instead.")
    print("Forwarding to new location...")
    
    # Forward to new module
    from src.dspy_optimization import compile as new_compile
    import runpy
    sys.argv[0] = new_compile.__file__
    runpy.run_module("src.dspy_optimization.compile", run_name="__main__")
