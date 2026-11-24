import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture(autouse=True)
def mock_background_execution(monkeypatch):
    """Prevents background tasks from launching live multi-step agent runs during API unit tests."""
    async def noop_execute(*args, **kwargs):
        pass
    monkeypatch.setattr("app.api.v1.runs._execute_agent_run", noop_execute)


def test_frontend_served_at_root():
    """Verifies that the interactive frontend HTML is served at GET /."""
    app = create_app()
    client = TestClient(app)

    res = client.get("/")
    assert res.status_code == 200
    assert "ARAA" in res.text
    assert "Autonomous Research & Analysis Agent" in res.text


def test_create_and_get_run_api():
    """Verifies API endpoints for creating and fetching research runs."""
    app = create_app()
    client = TestClient(app)

    # 1. Create run
    post_res = client.post(
        "/api/v1/runs",
        json={"task": "Find market price of ASML High NA EUV", "user_role": "researcher"},
    )
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["run_id"].startswith("run_")
    assert data["status"] == "queued"

    # 2. Get run details
    get_res = client.get(f"/api/v1/runs/{data['run_id']}")
    assert get_res.status_code == 200
    run_info = get_res.json()
    assert run_info["task"] == "Find market price of ASML High NA EUV"


def test_runs_session_isolation():
    """Verifies that research history is strictly isolated per client session and not leaked globally."""
    app = create_app()
    client = TestClient(app)

    # 1. Unauthenticated / untracked requests get empty list to protect privacy
    anon_res = client.get("/api/v1/runs")
    assert anon_res.status_code == 200
    assert anon_res.json() == []

    # 2. User A creates a run
    user_a_res = client.post(
        "/api/v1/runs",
        json={"task": "Secret Project A", "user_role": "researcher", "session_id": "sess_alice_123"},
    )
    assert user_a_res.status_code == 200
    run_a_id = user_a_res.json()["run_id"]

    # 3. User B creates a run
    user_b_res = client.post(
        "/api/v1/runs",
        json={"task": "Secret Project B", "user_role": "researcher", "session_id": "sess_bob_456"},
    )
    assert user_b_res.status_code == 200
    run_b_id = user_b_res.json()["run_id"]

    # 4. User A fetches their history
    history_a = client.get("/api/v1/runs?session_id=sess_alice_123").json()
    tasks_a = [r["task"] for r in history_a]
    assert "Secret Project A" in tasks_a
    assert "Secret Project B" not in tasks_a

    # 5. User B fetches their history
    history_b = client.get("/api/v1/runs?session_id=sess_bob_456").json()
    tasks_b = [r["task"] for r in history_b]
    assert "Secret Project B" in tasks_b
    assert "Secret Project A" not in tasks_b

    # 6. User B cannot access User A's run
    forbidden_res = client.get(f"/api/v1/runs/{run_a_id}?session_id=sess_bob_456")
    assert forbidden_res.status_code == 404

    # 7. User A deletes their history
    del_res = client.delete("/api/v1/runs?session_id=sess_alice_123")
    assert del_res.status_code == 200
    assert del_res.json()["cleared"] >= 1

    # 8. User A's history is gone, User B's remains intact
    history_a_after = client.get("/api/v1/runs?session_id=sess_alice_123").json()
    assert history_a_after == []
    history_b_after = client.get("/api/v1/runs?session_id=sess_bob_456").json()
    assert "Secret Project B" in [r["task"] for r in history_b_after]
