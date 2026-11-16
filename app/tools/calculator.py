import ast
import operator
from pydantic import BaseModel, Field

from app.tools.base import RiskLevel, ToolContext, ToolError, ToolResult


class CalculatorInput(BaseModel):
    """Input parameters for arithmetic calculation."""
    expression: str = Field(
        description="Math expression using basic operators (+, -, *, /, **), e.g. '100 * 12' or '500 / 4'"
    )


class CalculatorTool:
    """Safe arithmetic calculator evaluating math expressions via AST parsing."""

    name = "calculator"
    description = (
        "Calculates arithmetic expressions accurately. Use this whenever exact math, "
        "percentages, pricing totals, or sizing formulas are needed."
    )
    risk_level = RiskLevel.READ
    args_schema = CalculatorInput

    # Allowed safe operators
    _OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def _eval_node(self, node: ast.AST) -> float:
        """Safely evaluates an AST math node without using dangerous eval()."""
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self._OPERATORS:
                raise ToolError(f"Unsupported mathematical operator: {op_type.__name__}")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if op_type is ast.Div and right == 0:
                raise ToolError("Division by zero is undefined")
            return self._OPERATORS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self._OPERATORS:
                raise ToolError(f"Unsupported unary operator: {op_type.__name__}")
            operand = self._eval_node(node.operand)
            return self._OPERATORS[op_type](operand)
        else:
            raise ToolError(f"Unsupported syntax in expression: {type(node).__name__}")

    async def execute(self, args: CalculatorInput, ctx: ToolContext) -> ToolResult:
        """Executes safe calculation and returns result."""
        clean_expr = args.expression.strip()
        try:
            tree = ast.parse(clean_expr, mode="eval")
            result = self._eval_node(tree.body)
            # Format integer nicely if there is no decimal component
            formatted = str(int(result)) if result.is_integer() else f"{result:.4f}".rstrip("0").rstrip(".")
            return ToolResult(
                status="succeeded",
                content=formatted,
                trust_level="trusted",
            )
        except ToolError as te:
            return ToolResult(status="failed", content=f"Math error: {te.message}")
        except Exception as e:
            return ToolResult(status="failed", content=f"Syntax error in calculation: {str(e)}")
