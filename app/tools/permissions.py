from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.tools.base import RiskLevel


class UserRole(str, Enum):
    """User and tenant access control roles."""
    VIEWER = "viewer"
    RESEARCHER = "researcher"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass
class PolicyDecision:
    """Outcome of a zero-trust permission check."""
    allowed: bool
    requires_approval: bool
    reason: str


class PolicyEngine:
    """Deny-by-default permission engine enforcing role boundaries and risk tiers."""

    def __init__(
        self,
        auto_approved_risks_by_role: dict[UserRole, set[RiskLevel]] | None = None,
        approval_required_risks_by_role: dict[UserRole, set[RiskLevel]] | None = None,
    ):
        # Default least privilege matrix
        self.auto_approved = auto_approved_risks_by_role or {
            UserRole.VIEWER: {RiskLevel.READ},
            UserRole.RESEARCHER: {RiskLevel.READ, RiskLevel.READ_EXTERNAL},
            UserRole.OPERATOR: {RiskLevel.READ, RiskLevel.READ_EXTERNAL, RiskLevel.WRITE},
            UserRole.ADMIN: {RiskLevel.READ, RiskLevel.READ_EXTERNAL, RiskLevel.WRITE},
        }

        self.approval_required = approval_required_risks_by_role or {
            UserRole.VIEWER: set(),
            UserRole.RESEARCHER: {RiskLevel.WRITE, RiskLevel.EXTERNAL_EFFECT},
            UserRole.OPERATOR: {RiskLevel.EXTERNAL_EFFECT, RiskLevel.DANGEROUS},
            UserRole.ADMIN: {RiskLevel.EXTERNAL_EFFECT, RiskLevel.DANGEROUS},
        }

    def check(
        self,
        role: UserRole | str,
        tool_name: str,
        risk_level: RiskLevel,
        arguments: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluates whether an action is permitted, denied, or gated by human approval."""
        if isinstance(role, str):
            try:
                role = UserRole(role.lower())
            except ValueError:
                return PolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason=f"Unknown user role: '{role}' (Deny-by-default)",
                )

        auto_risks = self.auto_approved.get(role, set())
        approval_risks = self.approval_required.get(role, set())

        # 1. Check if explicitly auto-approved
        if risk_level in auto_risks:
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                reason=f"Auto-approved: Role '{role.value}' has direct access to '{risk_level.value}' actions.",
            )

        # 2. Check if gated behind human approval
        if risk_level in approval_risks:
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                reason=f"Approval required: Action '{tool_name}' has risk '{risk_level.value}' for role '{role.value}'.",
            )

        # 3. Deny by default
        return PolicyDecision(
            allowed=False,
            requires_approval=False,
            reason=f"Access denied: Role '{role.value}' is not authorized to execute '{risk_level.value}' tool '{tool_name}'.",
        )
