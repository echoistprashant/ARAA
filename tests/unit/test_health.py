def test_health_check(client):
    """Verifies that the /health endpoint responds with 200 and {'status': 'ok'}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-Request-ID" in response.headers


def test_api_v1_health_check(client):
    """Verifies that the /api/v1/health endpoint also responds correctly."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
