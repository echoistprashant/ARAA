from fastapi import Request
from fastapi.responses import JSONResponse


class ARAAError(Exception):
    """Base domain exception for ARAA."""

    def __init__(self, message: str, code: str = "internal_error", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(ARAAError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message=message, code="not_found", status_code=404)


class PermissionDeniedError(ARAAError):
    def __init__(self, message: str = "Action denied by policy"):
        super().__init__(message=message, code="permission_denied", status_code=403)


class BudgetExceededError(ARAAError):
    def __init__(self, message: str = "Budget ceiling reached"):
        super().__init__(message=message, code="budget_exceeded", status_code=429)


class ToolExecutionError(ARAAError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message=message, code="tool_execution_error", status_code=502)
        self.retryable = retryable


async def araa_exception_handler(request: Request, exc: ARAAError) -> JSONResponse:
    """Unified JSON error format for domain errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", "unknown"),
            }
        },
    )
