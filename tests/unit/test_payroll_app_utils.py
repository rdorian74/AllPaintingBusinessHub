from pathlib import Path

from tests.utils import load_flask_app


def test_payroll_app_db_and_hash(tmp_path, monkeypatch):
    db_path = tmp_path / "payroll.db"
    monkeypatch.setenv("PAYROLL_DB_PATH", str(db_path))

    app_module = load_flask_app(Path("payroll_app"))
    app_module.init_db()

    assert db_path.exists()

    sample_file = tmp_path / "sample.txt"
    sample_file.write_text("payroll data", encoding="utf-8")

    file_hash = app_module.get_file_hash(str(sample_file))
    assert file_hash
