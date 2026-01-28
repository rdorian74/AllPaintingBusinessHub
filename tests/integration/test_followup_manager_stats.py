from pathlib import Path

from tests.utils import load_flask_app


def test_followup_manager_stats(tmp_path, monkeypatch):
    db_path = tmp_path / "followup.db"
    monkeypatch.setenv("FOLLOWUP_MANAGER_DB_PATH", str(db_path))

    app_module = load_flask_app(Path("followup-manager"))
    client = app_module.app.test_client()

    response = client.get("/api/db/stats")
    data = response.get_json()

    assert response.status_code == 200
    assert "total_estimates" in data
