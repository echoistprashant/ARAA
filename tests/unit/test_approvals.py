import asyncio
from fastapi.testclient import TestClient

from app.api.v1.approvals import approval_service
from app.main import create_app
from app.services.approval_service import ApprovalService, ApprovalStatus


def test_approval_service_lifecycle_and_toctou_defense():
    """Verifies approval lifecycle and TOCTOU cryptographic argument tampering detection."""
    service = ApprovalService()

    # 1. Create request
    original_args = {"recipient": "finance@corp.internal", "amount": 5000}
    req = asyncio.run(service.create_request("run_99", "wire_transfer", original_args))

    assert req.status == ApprovalStatus.PENDING
    assert req.argument_hash is not None

    # 2. Approve request
    resolved = asyncio.run(service.resolve_request(req.approval_id, "approve", resolved_by="admin_alice"))
    assert resolved.status == ApprovalStatus.APPROVED

    # 3. Verify integrity with matching arguments
    assert service.verify_arguments_integrity(req.approval_id, original_args) is True

    # 4. TOCTOU defense: Tampered arguments must fail verification!
    tampered_args = {"recipient": "finance@corp.internal", "amount": 500000}
    assert service.verify_arguments_integrity(req.approval_id, tampered_args) is False


def test_approvals_api_endpoints():
    """Verifies HTTP endpoints for listing and resolving human approvals."""
    app = create_app()
    client = TestClient(app)

    # Seed an approval request directly into global approval_service
    req = asyncio.run(approval_service.create_request("run_api_test", "deploy_service", {"env": "prod"}))

    # GET pending approvals
    get_res = client.get(f"/api/v1/approvals/pending?run_id={req.run_id}")
    assert get_res.status_code == 200
    pending_list = get_res.json()
    assert any(item["approval_id"] == req.approval_id for item in pending_list)

    # POST resolve approval
    post_res = client.post(
        f"/api/v1/approvals/{req.approval_id}/resolve",
        json={"decision": "approve", "resolved_by": "security_officer"},
    )
    assert post_res.status_code == 200
    resolved_data = post_res.json()
    assert resolved_data["status"] == "approved"
    assert resolved_data["resolved_by"] == "security_officer"
