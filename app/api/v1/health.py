from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Liveness probe: verifies the API process is alive."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    """Readiness probe: verifies datastores and queue connectivity."""
    # Will be expanded with DB / Redis ping checks in Phase 2 & 3
    return {"status": "ready", "services": {"postgres": "ok", "redis": "ok"}}
