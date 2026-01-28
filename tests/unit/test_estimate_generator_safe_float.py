from pathlib import Path

from tests.utils import load_flask_app


def test_estimate_generator_safe_float():
    app_module = load_flask_app(Path("estimate-generator"))
    assert app_module.safe_float("$2,500") == 2500.0
    assert app_module.safe_float(None) == 0.0
