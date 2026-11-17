import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(BaseModel):
    """A durable human approval request with cryptographic TOCTOU protection."""
    approval_id: str
    run_id: str
    tool_name: str
    arguments: dict[str, Any]
    argument_hash: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str | None = None
    resolved_by: str | None = None
    rejection_reason: str | None = None


class ApprovalService:
    """Manages the lifecycle of Human-in-the-Loop (HITL) tool execution authorizations.
    
    Guarantees:
    - Time-of-Check to Time-of-Use (TOCTOU) defense: ensures arguments cannot be mutated post-approval.
    - Idempotent approval state transitions.
    """

    def __init__(self):
        self._approvals: dict[str, ApprovalRequest] = {}

    @staticmethod
    def compute_argument_hash(arguments: dict[str, Any]) -> str:
        """Computes a canonical SHA-256 hash of tool arguments to prevent TOCTOU tampering."""
        canonical = json.dumps(arguments, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def create_request(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ApprovalRequest:
        """Creates and persists a pending approval request."""
        approval_id = f"appr_{uuid.uuid4().hex[:10]}"
        arg_hash = self.compute_argument_hash(arguments)
        request = ApprovalRequest(
            approval_id=approval_id,
            run_id=run_id,
            tool_name=tool_name,
            arguments=arguments,
            argument_hash=arg_hash,
            status=ApprovalStatus.PENDING,
        )
        self._approvals[approval_id] = request
        return request

    async def get_request(self, approval_id: str) -> ApprovalRequest | None:
        """Fetches an approval request by ID."""
        return self._approvals.get(approval_id)

    async def list_pending(self, run_id: str | None = None) -> list[ApprovalRequest]:
        """Lists all pending approval requests, optionally filtered by run_id."""
        pending = [
            req for req in self._approvals.values()
            if req.status == ApprovalStatus.PENDING
        ]
        if run_id:
            pending = [req for req in pending if req.run_id == run_id]
        return pending

    async def resolve_request(
        self,
        approval_id: str,
        decision: str,  # "approve" or "reject"
        resolved_by: str = "operator",
        rejection_reason: str | None = None,
    ) -> ApprovalRequest:
        """Resolves a pending approval request."""
        req = self._approvals.get(approval_id)
        if not req:
            raise KeyError(f"Approval request {approval_id} not found.")

        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request {approval_id} is already resolved ({req.status.value}).")

        req.resolved_at = datetime.now(timezone.utc).isoformat()
        req.resolved_by = resolved_by

        if decision.lower() == "approve":
            req.status = ApprovalStatus.APPROVED
        elif decision.lower() == "reject":
            req.status = ApprovalStatus.REJECTED
            req.rejection_reason = rejection_reason or "Rejected by human reviewer."
        else:
            raise ValueError(f"Invalid decision '{decision}'. Must be 'approve' or 'reject'.")

        return req

    def verify_arguments_integrity(self, approval_id: str, current_arguments: dict[str, Any]) -> bool:
        """Verifies that the tool arguments being executed match the approved arguments exactly."""
        req = self._approvals.get(approval_id)
        if not req or req.status != ApprovalStatus.APPROVED:
            return False

        current_hash = self.compute_argument_hash(current_arguments)
        return current_hash == req.argument_hash
