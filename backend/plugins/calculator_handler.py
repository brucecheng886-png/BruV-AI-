"""
Calculator Plugin Handler
安全的數學計算（AST 白名單，不使用 eval）
支援動作: eval（或 calculate）
params: {expression: "2 + sqrt(16) * sin(pi/2)"}
"""
import ast
import math
import operator
import logging

logger = logging.getLogger(__name__)

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "log2": math.log2,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "exp": math.exp, "ceil": math.ceil, "floor": math.floor,
    "factorial": math.factorial, "gcd": math.gcd,
    "pi": math.pi, "e": math.e, "inf": math.inf, "tau": math.tau,
    "int": int, "float": float, "pow": pow,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, complex)):
            raise ValueError(f"不允許的常數類型: {type(node.value)}")
        return node.value
    elif isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCS:
            return _SAFE_FUNCS[node.id]
        raise ValueError(f"不允許的識別符: {node.id}")
    elif isinstance(node, ast.BinOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"不允許的運算符: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"不允許的一元運算符: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        func = _safe_eval(node.func)
        if callable(func):
            args = [_safe_eval(a) for a in node.args]
            return func(*args)
        raise ValueError("不允許的函式呼叫")
    elif isinstance(node, ast.List):
        return [_safe_eval(e) for e in node.elts]
    else:
        raise ValueError(f"不允許的語法節點: {type(node).__name__}")


async def run(action: str, params: dict, config: dict) -> dict:
    expr = params.get("expression") or params.get("query") or params.get("input", "")
    if not expr:
        return {"success": False, "error": "缺少 expression 參數，例：{\"expression\": \"sqrt(16) + 2**3\"}"}

    expr = str(expr).strip()
    try:
        tree = ast.parse(expr, mode="eval")
        result = _safe_eval(tree.body)

        # 格式化結果
        if isinstance(result, float):
            result_str = f"{result:.10g}"
        else:
            result_str = str(result)

        return {
            "success": True,
            "data": {
                "expression": expr,
                "result": result,
                "result_str": result_str,
            },
        }
    except ZeroDivisionError:
        return {"success": False, "error": "除以零"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except SyntaxError:
        return {"success": False, "error": f"算式語法錯誤: {expr}"}
    except Exception as e:
        logger.error("Calculator error: %s", e)
        return {"success": False, "error": f"計算失敗: {e}"}
