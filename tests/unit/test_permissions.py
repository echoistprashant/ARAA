from app.tools.base import RiskLevel
from app.tools.permissions import PolicyEngine, UserRole


def test_policy_engine_viewer_least_privilege():
    """Verifies viewer role permissions."""
    engine = PolicyEngine()

    # Read allowed
    dec = engine.check(UserRole.VIEWER, "calculator", RiskLevel.READ)
    assert dec.allowed is True
    assert dec.requires_approval is False

    # Read external denied for viewer
    dec = engine.check(UserRole.VIEWER, "web_search", RiskLevel.READ_EXTERNAL)
    assert dec.allowed is False

    # Write denied for viewer
    dec = engine.check(UserRole.VIEWER, "save_file", RiskLevel.WRITE)
    assert dec.allowed is False


def test_policy_engine_researcher_approval_gating():
    """Verifies researcher auto-approves read tools but gates side effects."""
    engine = PolicyEngine()

    # Read external auto-approved
    dec = engine.check(UserRole.RESEARCHER, "web_search", RiskLevel.READ_EXTERNAL)
    assert dec.allowed is True
    assert dec.requires_approval is False

    # Write requires human approval
    dec = engine.check(UserRole.RESEARCHER, "file_write", RiskLevel.WRITE)
    assert dec.allowed is True
    assert dec.requires_approval is True
    assert "Approval required" in dec.reason

    # Dangerous denied
    dec = engine.check(UserRole.RESEARCHER, "delete_db", RiskLevel.DANGEROUS)
    assert dec.allowed is False


def test_policy_engine_unknown_role_denied():
    """Verifies deny-by-default on unrecognized roles."""
    engine = PolicyEngine()
    dec = engine.check("hacker_role", "calculator", RiskLevel.READ)
    assert dec.allowed is False
    assert "Unknown user role" in dec.reason
