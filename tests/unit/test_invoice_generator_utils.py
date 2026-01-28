from pathlib import Path

from tests.utils import load_flask_app


def test_invoice_generator_numbering(tmp_path):
    app_module = load_flask_app(Path("invoice-generator"))
    counter_file = tmp_path / "counter.json"
    app_module.COUNTER_FILE = counter_file

    first = app_module.get_next_invoice_number("25C")
    second = app_module.get_next_invoice_number("25C")

    assert first == "25C-001"
    assert second == "25C-002"


def test_invoice_generator_safe_float():
    app_module = load_flask_app(Path("invoice-generator"), module_prefix="invoice")
    assert app_module.safe_float("$1,234.50") == 1234.5
    assert app_module.safe_float("") == 0.0
