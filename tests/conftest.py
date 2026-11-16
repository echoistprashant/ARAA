import pytest
from starlette.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client():
    """Provides a test client for unit tests."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
