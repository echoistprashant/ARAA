import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.approvals import router as approvals_router
from app.api.v1.health import router as health_router
from app.core.config import settings
from app.core.errors import ARAAError, araa_exception_handler
from app.core.logging import get_logger, setup_logging

logger = get_logger("araa.main")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates an X-Request-ID header to every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle management."""
    setup_logging(debug=settings.DEBUG)
    logger.info("araa_startup", env=settings.APP_ENV, provider=settings.LLM_PROVIDER)
    yield
    logger.info("araa_shutdown")


def create_app() -> FastAPI:
    """Factory function creating the configured FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="Autonomous Research & Analysis Agent (ARAA) API",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    # Exception Handlers
    app.add_exception_handler(ARAAError, araa_exception_handler)

    # Routers
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")

    return app


app = create_app()
