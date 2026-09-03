"""Live KiCad SWIG Oracle alias (kaibridge.oracle.swig_oracle).
Re-exports the core SWIG signature, class, and architectural oracle from kaibridge.core.oracle.
"""
from ..core.oracle import (
    query_oracle,
    resolve_api_symbol,
    get_class_methods,
    get_all_classes,
    get_architecture_rules,
    BENCHMARK_PROMPTS
)

__all__ = [
    "query_oracle",
    "resolve_api_symbol",
    "get_class_methods",
    "get_all_classes",
    "get_architecture_rules",
    "BENCHMARK_PROMPTS"
]
