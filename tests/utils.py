import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path


def load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def temporary_sys_path(path: Path):
    sys.path.insert(0, str(path))
    try:
        yield
    finally:
        if sys.path[0] == str(path):
            sys.path.pop(0)


def load_flask_app(app_dir: Path, app_filename: str = "app.py", module_prefix: str = "app"):
    app_dir = Path(app_dir)
    app_path = app_dir / app_filename
    unique_prefix = f"{module_prefix}_{app_dir.name.replace('-', '_')}"

    for key in ["config", "database", "db"]:
        sys.modules.pop(key, None)

    with temporary_sys_path(app_dir):
        module = load_module(unique_prefix, app_path)

    for key in ["config", "database", "db"]:
        sys.modules.pop(key, None)

    return module
