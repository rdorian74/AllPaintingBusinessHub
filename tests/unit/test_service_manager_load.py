from pathlib import Path

from hub_utils.service_manager import load_services


def test_load_services_config():
    config_path = Path("hub-config/main_services.json")
    data = load_services(config_path)
    services = data["services"]
    assert "ai-agent" in services
    assert services["ai-agent"]["port"] == 5011
