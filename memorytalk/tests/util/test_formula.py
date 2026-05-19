"""Unit tests for util/formula.py — safe AST-whitelist formula evaluator."""
from __future__ import annotations
import math
import pytest

from memorytalk.util.formula import FormulaError, compile_formula


class TestCompile:
    def test_simple_arithmetic(self):
        f = compile_formula("1 + 2 * 3")
        assert f({}) == 7

    def test_unary_minus(self):
        f = compile_formula("-x + 5")
        assert f({"x": 3}) == 2

    def test_default_v3_formula(self):
        f = compile_formula(
            "relevance + 0.1 * (review_up - review_down) "
            "+ 0.02 * log(read_count + 1) - 0.005 * age_days"
        )
        # Plug in numbers that roughly match a "popular card" scenario.
        env = {"relevance": 0.5, "review_up": 7, "review_down": 3,
               "read_count": 42, "age_days": 10}
        val = f(env)
        expected = 0.5 + 0.1 * 4 + 0.02 * math.log(43) - 0.005 * 10
        assert abs(val - expected) < 1e-9

    def test_missing_var_defaults_to_zero(self):
        # Sessions don't have card-stat fields — the formula should still
        # evaluate with those treated as 0 (docs/cli/v3/search.md guarantee).
        f = compile_formula("relevance + review_up + read_count")
        assert f({"relevance": 0.5}) == pytest.approx(0.5)

    def test_pow_and_min_max(self):
        f = compile_formula("max(pow(x, 2), 10)")
        assert f({"x": 5}) == 25
        assert f({"x": 2}) == 10


class TestReject:
    def test_syntax_error(self):
        with pytest.raises(FormulaError, match="syntax"):
            compile_formula("1 + ")

    def test_attribute_access_rejected(self):
        # Trying to escape into __import__ / os via attribute lookup.
        with pytest.raises(FormulaError):
            compile_formula("x.__class__")

    def test_subscript_rejected(self):
        with pytest.raises(FormulaError):
            compile_formula("x[0]")

    def test_unknown_function_rejected(self):
        # ``__import__`` would be the obvious escape.
        with pytest.raises(FormulaError, match="unknown function"):
            compile_formula("__import__('os')")

    def test_lambda_rejected(self):
        with pytest.raises(FormulaError):
            compile_formula("(lambda: 1)()")

    def test_call_on_non_name_rejected(self):
        # ``(x)(y)`` — calling a non-Name expression.
        with pytest.raises(FormulaError):
            compile_formula("(x)(5)")

    def test_keyword_arg_rejected(self):
        # log() taking a keyword arg → not allowed.
        with pytest.raises(FormulaError, match="keyword"):
            compile_formula("log(x=1)")

    def test_string_literal_rejected(self):
        # Constants must be numeric.
        with pytest.raises(FormulaError):
            compile_formula("'foo'")


class TestEvaluation:
    def test_evaluation_error_wrapped(self):
        # Division by zero at runtime.
        f = compile_formula("1 / x")
        with pytest.raises(FormulaError, match="evaluation"):
            f({"x": 0})
