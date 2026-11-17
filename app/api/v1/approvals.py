from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.approval_service import ApprovalRequest, ApprovalService

router = APIRouter(prefix="/approvals", tags=["approvals"])

# Global singleton service for in-memory execution and integration
approval_service = ApprovalService()


class ResolveApprovalPayload(BaseModel):
    decision: Literal["approve", "reject"]
    resolved_by: str = "human_operator"
    rejection_reason: str | None = None


@router.get("/pending", response_model=list[ApprovalRequest])
async def list_pending_approvals(run_id: str | None = Query(None, description="Optional run ID filter")):
    """Retrieves all tool execution requests awaiting human authorization."""
    return await approval_service.list_pending(run_id=run_id)


@router.post("/{approval_id}/resolve", response_model=ApprovalRequest)
async def resolve_approval(approval_id: str, payload: ResolveApprovalPayload):
    """Authorizes or denies a pending tool execution."""
    try:
        resolved = await approval_service.resolve_request(
            approval_id=approval_id,
            decision=payload.decision,
            resolved_by=payload.resolved_by,
            rejection_reason=payload.rejection_reason,
        )
        return resolved
    except KeyError:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
