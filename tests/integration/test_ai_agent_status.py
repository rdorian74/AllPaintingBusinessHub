import os
from pathlib import Path

from tests.utils import load_flask_app


def test_ai_agent_status_endpoint(tmp_path, monkeypatch):
    db_path = tmp_path / "agent.db"
    monkeypatch.setenv("AI_AGENT_DB_PATH", str(db_path))

    app_module = load_flask_app(Path("ai-agent"))
    app_module.db.init_database()

    client = app_module.app.test_client()
    response = client.get("/api/status")
    data = response.get_json()

    assert response.status_code == 200
    assert data["running"] is True
    assert "stats" in data
