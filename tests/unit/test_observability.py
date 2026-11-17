import asyncio

from app.api.v1.events import EventBroadcaster
from app.llm.client import ChatMessage, LLMResponse, Role, TokenUsage
from app.observability.langfuse_adapter import LangfuseAdapter
from app.observability.tracing import Tracer


def test_tracer_nested_spans():
    """Verifies span stack hierarchy and attribute propagation."""
    tracer = Tracer()

    with tracer.start_span("agent_run", {"run_id": "run_123"}) as root_span:
        assert root_span.status == "UNSET"

        with tracer.start_span("step_1", {"step_idx": 1}) as step_span:
            step_span.set_attribute("tool", "web_search")
            step_span.add_event("query_dispatched", {"q": "quantum"})
            assert step_span.parent_span_id == root_span.span_id

    spans = tracer.get_spans()
    assert len(spans) == 2
    assert spans[0].name == "step_1"
    assert spans[0].status == "OK"
    assert spans[1].name == "agent_run"
    assert spans[1].status == "OK"


def test_langfuse_adapter_token_accounting():
    """Verifies generation logging and token cost aggregations."""
    adapter = LangfuseAdapter()
    messages = [ChatMessage(role=Role.USER, content="Hello")]
    response = LLMResponse(
        content="World",
        usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15, cost_usd=0.00003),
    )

    record = adapter.log_generation(
        trace_id="tr_1",
        generation_id="gen_1",
        model="gemini-2.0-flash",
        messages=messages,
        response=response,
        latency_ms=120.5,
    )

    assert record.prompt_tokens == 10
    assert record.completion_tokens == 5
    assert record.total_tokens == 15

    summary = adapter.get_summary()
    assert summary["total_generations"] == 1
    assert summary["total_tokens"] == 15
    assert summary["total_cost_usd"] == 0.00003


def test_event_broadcaster_pub_sub():
    """Verifies that published events reach subscribers."""
    broadcaster = EventBroadcaster()
    queue = broadcaster.subscribe("run_abc")

    async def publish_and_receive():
        await broadcaster.publish("run_abc", "step_started", {"step": 1})
        msg = await queue.get()
        return msg

    msg = asyncio.run(publish_and_receive())
    assert msg["event"] == "step_started"
    assert msg["data"]["step"] == 1
    broadcaster.unsubscribe("run_abc", queue)
