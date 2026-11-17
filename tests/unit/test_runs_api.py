from fastapi.testclient import TestClient
from app.main import create_app


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
