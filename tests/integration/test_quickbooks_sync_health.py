from pathlib import Path

from tests.utils import load_flask_app


def test_quickbooks_sync_health():
    app_module = load_flask_app(Path("quickbooks-sync"))
    client = app_module.app.test_client()
    response = client.get("/api/health")
    data = response.get_json()

    assert response.status_code == 200
    assert data["status"] == "healthy"
