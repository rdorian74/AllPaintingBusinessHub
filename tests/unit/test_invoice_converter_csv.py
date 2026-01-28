from pathlib import Path

from tests.utils import load_flask_app


def test_convert_to_quickbooks_csv():
    app_module = load_flask_app(Path("invoice_converter"))

    invoices = [
        {
            "invoice_no": "INV-001",
            "customer": "Test Customer",
            "invoice_date": "01/02/2026",
            "due_date": "01/03/2026",
            "subtotal": 100.0,
            "gst_amount": 5.0,
            "total": 105.0,
            "line_items": [
                {
                    "item": "Labor",
                    "description": "Painting work",
                    "quantity": 10,
                    "rate": 10,
                    "amount": 100.0,
                }
            ],
        }
    ]

    rows = app_module.convert_to_quickbooks_csv(invoices)

    assert rows[0]["*InvoiceNo"] == "INV-001"
    assert rows[0]["*Customer"] == "Test Customer"
    assert "Painting work" in rows[0]["ItemDescription"]
