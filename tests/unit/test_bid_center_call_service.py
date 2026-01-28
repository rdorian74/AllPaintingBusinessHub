from pathlib import Path

from tests.utils import load_flask_app


def test_bid_center_call_service_get(monkeypatch):
    app_module = load_flask_app(Path("bid-system-v2/bid-center"))

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, timeout=30):
        assert "/api/status" in url
        return DummyResponse({"ok": True})

    monkeypatch.setattr(app_module.requests, "get", fake_get)

    result = app_module.call_service("email_scanner", "/api/status")
    assert result["ok"] is True
