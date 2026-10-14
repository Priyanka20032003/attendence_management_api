from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_app_is_created():
    assert app is not None
    assert client is not None
