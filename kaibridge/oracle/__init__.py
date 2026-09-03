"""Live KiCad SWIG Oracle package."""
from .swig_oracle import (
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
