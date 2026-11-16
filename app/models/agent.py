from datetime import datetime, timezone
import uuid
from typing import Any
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class AgentRunModel(Base):
    """Database representation of an agent research run."""
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, default="default_tenant", index=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    task = Column(Text, nullable=False)
    status = Column(
        String(32),
        nullable=False,
        default="queued",
        index=True,
    )
    config = Column(JSONB, nullable=False, default=dict)
    plan = Column(JSONB, nullable=True)
    final_report = Column(Text, nullable=True)
    step_count = Column(Integer, default=0, nullable=False)
    input_tokens = Column(BigInteger, default=0, nullable=False)
    output_tokens = Column(BigInteger, default=0, nullable=False)
    cost_usd = Column(Numeric(12, 6), default=0.0, nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    steps = relationship("RunStepModel", back_populates="run", cascade="all, delete-orphan", order_by="RunStepModel.idx")
    tool_calls = relationship("ToolCallModel", back_populates="run", cascade="all, delete-orphan")
    evidence = relationship("EvidenceItemModel", back_populates="run", cascade="all, delete-orphan")


class RunStepModel(Base):
    """Ordered chronological steps within an agent run."""
    __tablename__ = "run_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    idx = Column(Integer, nullable=False)
    kind = Column(String(32), nullable=False)  # plan, llm, tool, approval, verify, final
    llm_model = Column(String(64), nullable=True)
    prompt_version = Column(String(32), nullable=True)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    content = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    run = relationship("AgentRunModel", back_populates="steps")

    __table_args__ = (
        UniqueConstraint("run_id", "idx", name="uq_run_step_idx"),
    )


class ToolCallModel(Base):
    """Durable record of a tool invocation for idempotency and auditability."""
    __tablename__ = "tool_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(UUID(as_uuid=True), ForeignKey("run_steps.id", ondelete="SET NULL"), nullable=True)
    tool_name = Column(String(64), nullable=False)
    tool_source = Column(String(32), default="local", nullable=False)  # local, mcp, sandbox
    arguments = Column(JSONB, nullable=False, default=dict)
    idempotency_key = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(32), default="pending", nullable=False)
    result_summary = Column(Text, nullable=True)
    error_class = Column(String(64), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("AgentRunModel", back_populates="tool_calls")


class EvidenceItemModel(Base):
    """Persisted factual evidence collected by tools during research."""
    __tablename__ = "evidence_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(64), nullable=False)
    source_url = Column(Text, nullable=True)
    query = Column(Text, nullable=True)
    excerpt = Column(Text, nullable=False)
    trust_level = Column(String(32), default="untrusted", nullable=False)
    collected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    run = relationship("AgentRunModel", back_populates="evidence")
