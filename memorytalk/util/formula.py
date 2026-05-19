"""Safe AST-whitelist arithmetic formula compiler.

The search ranking formula lives in user-editable ``settings.search.ranking_formula``.
Users put arithmetic expressions there; we need to evaluate them per
candidate without exposing a generic Python ``eval``. This module:

- Parses the formula once via ``ast.parse(..., mode='eval')``.
- Walks the tree and rejects any node not on the whitelist.
- Returns a closure that evaluates the expression against a variable dict.

Allowed node types are limited to arithmetic / unary / function calls
against a small whitelist of math functions. Anything that could touch
the host environment (Name lookups outside the variable dict, attribute
access, subscripting, comprehensions, ...) is rejected at compile time.
"""
from __future__ import annotations
import ast
import math
import operator as op
from typing import Callable


_BINOP = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}

_UNARY = {
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

# Math helpers exposed to formula authors. Conservative — add only when
# someone actually needs them, so the surface area stays small.
_FUNCS: dict[str, Callable] = {
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "sqrt": math.sqrt,
    "pow": math.pow,
    "min": min,
    "max": max,
    "abs": abs,
}


class FormulaError(ValueError):
    """Raised on parse / validation / evaluation errors."""


def compile_formula(expr: str) -> Callable[[dict[str, float]], float]:
    """Compile a formula string into a callable ``vars → float``.

    Validation is upfront — a compile-time call raises ``FormulaError`` on
    any unsupported node; subsequent evaluations against runtime variable
    dicts are cheap (a single AST walk via an interpreter).
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"formula syntax error: {e.msg}") from e

    _validate(tree.body)

    def evaluate(variables: dict[str, float]) -> float:
        try:
            return _eval(tree.body, variables)
        except Exception as e:
            raise FormulaError(f"formula evaluation failed: {e}") from e

    return evaluate


def _validate(node: ast.AST) -> None:
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOP:
            raise FormulaError(f"unsupported binary operator: {type(node.op).__name__}")
        _validate(node.left)
        _validate(node.right)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise FormulaError(f"unsupported unary operator: {type(node.op).__name__}")
        _validate(node.operand)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("only direct function calls are allowed")
        if node.func.id not in _FUNCS:
            raise FormulaError(f"unknown function: {node.func.id!r}")
        if node.keywords:
            raise FormulaError("keyword arguments are not allowed in formula")
        for arg in node.args:
            _validate(arg)
    elif isinstance(node, ast.Name):
        # Variables get filled in at eval time; identifier itself is fine.
        return
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise FormulaError(f"only numeric literals are allowed, got {type(node.value).__name__}")
    else:
        raise FormulaError(f"unsupported node type: {type(node).__name__}")


def _eval(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.BinOp):
        return _BINOP[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.Call):
        return _FUNCS[node.func.id](*[_eval(a, env) for a in node.args])
    if isinstance(node, ast.Name):
        # Missing variables default to 0 — matches docs/cli/v3/search.md
        # where stat fields are "sessions 桶 statistics 全部置 0".
        return float(env.get(node.id, 0.0))
    if isinstance(node, ast.Constant):
        return float(node.value)
    raise FormulaError(f"cannot evaluate node: {type(node).__name__}")
