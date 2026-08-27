"""
Safe AST-based mathematical string evaluation utility.
"""

import ast
import operator as op
from typing import Any

MATH_OPERATORS: dict[type, Any] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Mod: op.mod,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def safe_eval_math(expr_str: str) -> float | None:
    """Safely evaluates basic mathematical string expressions without using eval()."""
    clean_expr = expr_str.replace("грн", "").replace("g", "").replace("г", "").replace(",", ".").strip()
    if not clean_expr:
        return None
    try:
        node = ast.parse(clean_expr, mode="eval").body

        def _eval(n: ast.AST) -> float:
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            elif isinstance(n, ast.BinOp):
                left_val = _eval(n.left)
                right_val = _eval(n.right)
                return MATH_OPERATORS[type(n.op)](left_val, right_val)
            elif isinstance(n, ast.UnaryOp):
                return MATH_OPERATORS[type(n.op)](_eval(n.operand))
            raise ValueError("Unsupported syntax")

        result = _eval(node)
        return round(float(result), 2)
    except Exception:
        return None
