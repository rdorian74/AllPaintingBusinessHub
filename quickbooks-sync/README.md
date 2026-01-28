# QuickBooks Sync Service

All Painting Ltd - Invoice Integration with QuickBooks Online

## Quick Setup

### 1. Configure Credentials

Edit `config.py` and fill in your credentials:

```python
CLIENT_ID = "your_client_id_here"
CLIENT_SECRET = "your_client_secret_here"
COMPANY_ID = "your_company_id_here"
```

### 2. Run the Service

Double-click `run_quickbooks_sync.bat`

Or manually:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### 3. Authorize the App

1. Open http://localhost:5010 in your browser
2. Click "Connect to QuickBooks"
3. Log in to your QuickBooks account
4. Authorize the app
5. You'll be redirected back - should show "Connected"

## API Endpoints

### Create Invoice
```
POST http://localhost:5015/api/create-invoice
Content-Type: application/json

{
    "invoice_number": "26C-004",
    "estimate_number": "25C-326",
    "client_company": "Guildford Town Centre Limited",
    "client_contact": "Curtis Darrah",
    "client_email": "c.darrah@jll.com",
    "client_phone": "604-374-8095",
    "client_address": "10355 152nd Street, Surrey, BC, V3R 7C1",
    "project_name": "Painting walls",
    "project_address": "10355 152nd St., Suite 2695, Surrey",
    "po_number": "2026-049",
    "line_items": [
        {"description": "Painting of storefront walls", "amount": 2162.00}
    ],
    "subtotal": 2162.00,
    "pdf_path": "C:\\path\\to\\invoice.pdf"
}
```

### Check Status
```
GET http://localhost:5015/api/status
```

### Health Check
```
GET http://localhost:5015/api/health
```

## Integration with Estimate Automation

The Invoice Generator and Estimate Automation dashboard will call this service
to create invoices in QuickBooks with a single button click.

## Switching to Production

When ready to use with your real QuickBooks:

1. Go to Intuit Developer Portal
2. Get Production keys (Keys & credentials → Production)
3. Update `config.py`:
   - Set `CLIENT_ID` and `CLIENT_SECRET` to production values
   - Set `COMPANY_ID` to your real company ID
   - Set `USE_SANDBOX = False`
4. Re-authorize the app

## Troubleshooting

**"Not authenticated" error:**
- Visit http://localhost:5015 and click "Connect to QuickBooks"

**"Token expired" error:**
- The service auto-refreshes tokens, but if refresh fails, reconnect via dashboard

**"Customer not found" creating invoice:**
- The service auto-creates customers if not found in QuickBooks

**PDF not attaching:**
- Ensure the PDF path is accessible from the server
- Check file permissions
