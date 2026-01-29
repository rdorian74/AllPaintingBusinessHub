import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_psutil():
    try:
        import psutil  # type: ignore
    except ImportError:
        return None
    return psutil


def resolve_path(path_value: str) -> Path:
    if not path_value:
        raise ValueError("Service path is required")
    expanded = path_value.replace("$REPO_ROOT", str(REPO_ROOT))
    path = Path(expanded)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def load_services(config_path: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    services = data.get("services", {})
    hub_name = data.get("hub_name", "Business Hub")
    return {"hub_name": hub_name, "services": services}


def is_port_in_use(port: int) -> bool:
    if not port:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _python_for_service(service_path: Path, prefer_venv: bool) -> Path:
    if prefer_venv:
        if os.name == "nt":
            candidate = service_path / "venv" / "Scripts" / "python.exe"
        else:
            candidate = service_path / "venv" / "bin" / "python"
        if candidate.exists():
            return candidate
    return Path(os.environ.get("BUSINESS_HUB_PYTHON", sys.executable))


class ServiceManager:
    def __init__(self, services: dict, runtime_dir: Path, logs_dir: Path):
        self._psutil = _load_psutil()
        self.services = services
        self.runtime_dir = runtime_dir
        self.logs_dir = logs_dir
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.pid_store_path = self.runtime_dir / "service_pids.json"
        self._pids = self._load_pids()
        if self._psutil is None:
            print(
                "Warning: psutil is not installed. Process management will be limited; "
                "install psutil to enable full start/stop controls.",
                file=sys.stderr,
            )

    def _load_pids(self) -> dict:
        if self.pid_store_path.exists():
            try:
                with open(self.pid_store_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_pids(self) -> None:
        with open(self.pid_store_path, "w", encoding="utf-8") as handle:
            json.dump(self._pids, handle, indent=2)

    def _service_process(self, pid: int):
        psutil = self._psutil
        if not pid:
            return None
        if psutil is None:
            return None
        if psutil.pid_exists(pid):
            try:
                return psutil.Process(pid)
            except psutil.Error:
                return None
        return None

    def get_status(self, service_id: str) -> bool:
        service = self.services[service_id]
        pid = self._pids.get(service_id)
        process = self._service_process(pid)
        if process and process.is_running():
            return True
        port = service.get("port")
        return is_port_in_use(port)

    def get_all_statuses(self) -> dict:
        return {service_id: self.get_status(service_id) for service_id in self.services}

    def start_service(self, service_id: str) -> dict:
        service = self.services[service_id]
        service_path = resolve_path(service["path"])
        script = service["script"]
        python_exe = _python_for_service(service_path, service.get("has_venv", False))

        env = os.environ.copy()
        env.update(service.get("env", {}))
        env.setdefault("PYTHONUNBUFFERED", "1")

        log_file = self.logs_dir / f"{service_id}.log"
        log_handle = open(log_file, "a", encoding="utf-8")

        command = [str(python_exe), script]

        popen_kwargs = {
            "cwd": str(service_path),
            "stdout": log_handle,
            "stderr": log_handle,
            "env": env,
        }

        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **popen_kwargs)
        self._pids[service_id] = process.pid
        self._save_pids()
        return {"success": True, "pid": process.pid}

    def stop_service(self, service_id: str) -> dict:
        service = self.services[service_id]
        pid = self._pids.get(service_id)
        psutil = self._psutil
        process = self._service_process(pid)

        if psutil is None:
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
        elif process:
            for child in process.children(recursive=True):
                try:
                    child.terminate()
                except psutil.Error:
                    pass
            try:
                process.terminate()
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                process.kill()
            except psutil.Error:
                pass

        if psutil is not None and service.get("port"):
            self._kill_by_port(service["port"])

        self._pids.pop(service_id, None)
        self._save_pids()
        return {"success": True}

    def _kill_by_port(self, port: int) -> None:
        psutil = self._psutil
        if psutil is None:
            return
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr and conn.laddr.port == port and conn.pid:
                    try:
                        proc = psutil.Process(conn.pid)
                        proc.send_signal(signal.SIGTERM)
                        proc.wait(timeout=3)
                    except psutil.Error:
                        pass
        except psutil.Error:
            return
