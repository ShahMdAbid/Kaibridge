"""Tests for kaibridge.oracle and kaibridge.core.oracle."""
from __future__ import annotations

import pytest
from kaibridge.oracle.swig_oracle import (
    query_oracle,
    resolve_api_symbol,
    get_architecture_rules,
    get_all_classes,
    BENCHMARK_PROMPTS
)


class TestOracle:
    def test_rules_listing(self):
        res = query_oracle("topics")
        assert res.get("success") is True
        assert res.get("type") == "TOPICS_LIST"
        assert res.get("count", 0) >= 8
        topics = [t["key"] for t in res.get("topics", [])]
        assert "drc_rules" in topics
        assert "jlcpcb_rules" in topics
        assert "swig_memory" in topics

    def test_specific_rule_retrieval(self):
        res = resolve_api_symbol("jlcpcb_rules")
        assert res.get("success") is True
        assert res.get("type") == "RULE"
        details = res.get("details", {})
        assert "rules" in details
        assert len(details["rules"]) > 0

    def test_swig_memory_rules(self):
        rules = get_architecture_rules()
        assert "swig_memory" in rules
        mem_rules = rules["swig_memory"]["rules"]
        assert any("gc.collect()" in r for r in mem_rules)
        assert any("del board" in r for r in mem_rules)

    def test_empty_query_fails_cleanly(self):
        res = query_oracle("")
        assert res.get("success") is False
        assert "Empty query" in res.get("error", "")

    def test_benchmark_prompts_present(self):
        assert len(BENCHMARK_PROMPTS) >= 5
        assert "ExportSpecctraDSN" in BENCHMARK_PROMPTS
