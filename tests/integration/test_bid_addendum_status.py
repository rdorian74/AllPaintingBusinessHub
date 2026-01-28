from pathlib import Path

from tests.utils import load_flask_app


def test_bid_addendum_status_endpoint(tmp_path, monkeypatch):
    db_path = tmp_path / "bid_agent.db"
    monkeypatch.setenv("BID_ADDENDUM_DB_PATH", str(db_path))

    app_module = load_flask_app(Path("bid-addendum-agent"), app_filename="main.py")
    app_module.db = app_module.Database()

    client = app_module.app.test_client()
    response = client.get("/api/status")
    data = response.get_json()

    assert response.status_code == 200
    assert "mode" in data
    assert "stats" in data
