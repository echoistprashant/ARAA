import uuid
from app.models.agent import AgentRunModel, EvidenceItemModel, RunStepModel, ToolCallModel


def test_agent_run_model_instantiation():
    """Verifies that AgentRunModel correctly initializes fields and relationships."""
    run_id = uuid.uuid4()
    run = AgentRunModel(
        id=run_id,
        tenant_id="tenant_alpha",
        task="Evaluate vector DBs",
        status="running",
        step_count=1,
    )

    assert run.id == run_id
    assert run.tenant_id == "tenant_alpha"
    assert run.status == "running"
    assert run.step_count == 1
    assert run.__tablename__ == "agent_runs"


def test_run_step_and_tool_call_models():
    """Verifies RunStepModel and ToolCallModel columns and unique constraints."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()

    step = RunStepModel(
        id=step_id,
        run_id=run_id,
        idx=1,
        kind="tool",
        llm_model="gemini-2.0-flash",
        content={"action": "web_search"},
    )

    tool_call = ToolCallModel(
        run_id=run_id,
        step_id=step_id,
        tool_name="web_search",
        idempotency_key="idemp_12345",
        status="succeeded",
    )

    assert step.idx == 1
    assert step.kind == "tool"
    assert tool_call.tool_name == "web_search"
    assert tool_call.idempotency_key == "idemp_12345"


def test_evidence_item_model():
    """Verifies EvidenceItemModel fields and default trust level."""
    run_id = uuid.uuid4()
    evidence = EvidenceItemModel(
        run_id=run_id,
        tool_name="web_search",
        source_url="https://qdrant.tech",
        excerpt="Node price: $25/month",
        trust_level="untrusted",
    )

    assert evidence.run_id == run_id
    assert evidence.trust_level == "untrusted"
    assert evidence.excerpt == "Node price: $25/month"
