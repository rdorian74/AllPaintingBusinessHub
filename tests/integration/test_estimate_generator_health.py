from pathlib import Path

from tests.utils import load_flask_app


def test_estimate_generator_health():
    app_module = load_flask_app(Path("estimate-generator"))
    client = app_module.app.test_client()
    response = client.get("/api/health")
    data = response.get_json()

    assert response.status_code == 200
    assert data["status"] == "healthy"
