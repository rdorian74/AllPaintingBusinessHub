from pathlib import Path

from hub_utils.service_manager import load_services, resolve_path


def test_service_paths_exist():
    config_path = Path("hub-config/main_services.json")
    data = load_services(config_path)

    for service_id, service in data["services"].items():
        path = resolve_path(service["path"])
        script_path = path / service["script"]
        assert path.exists(), f"{service_id} path missing"
        assert script_path.exists(), f"{service_id} script missing"
