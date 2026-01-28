from pathlib import Path

from tests.utils import load_flask_app


def test_invoice_converter_convert_endpoint():
    app_module = load_flask_app(Path("invoice_converter"))
    client = app_module.app.test_client()

    payload = {
        "invoices": [
            {
                "invoice_no": "INV-002",
                "customer": "Demo Customer",
                "invoice_date": "05/02/2026",
                "due_date": "05/03/2026",
                "subtotal": 200.0,
                "gst_amount": 10.0,
                "total": 210.0,
                "line_items": [
                    {
                        "item": "Labor",
                        "description": "Prep",
                        "quantity": 5,
                        "rate": 40,
                        "amount": 200.0,
                    }
                ],
            }
        ]
    }

    response = client.post("/convert", json=payload)
    data = response.get_json()

    assert response.status_code == 200
    assert data["success"] is True
    assert "csv" in data
