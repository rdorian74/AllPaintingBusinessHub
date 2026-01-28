# Invoice to QuickBooks CSV Converter

Converts PDF and Word invoices to QuickBooks import CSV format using Claude AI for intelligent data extraction.

## Setup

1. Install dependencies:
```bash
pip install flask pdfplumber python-docx anthropic
```

2. Configure your Anthropic API key (choose one method):

   **Option A: Environment variable (recommended)**
   ```bash
   export ANTHROPIC_API_KEY=your_api_key_here
   ```

   **Option B: Config file**
   - Copy `config.json.example` to `config.json`
   - Replace `YOUR_ANTHROPIC_API_KEY_HERE` with your actual API key

3. Run the application:
```bash
python app.py
```

4. Open http://localhost:5005 in your browser

## Usage

1. Drag and drop PDF or DOCX invoice files into the upload zone
2. Review and edit the AI-extracted data if needed
3. Click "Preview CSV" to see the QuickBooks format
4. Click "Download CSV" to get the file for import

## QuickBooks CSV Format

Mandatory fields (marked with *):
- *InvoiceNo
- *Customer
- *InvoiceDate (DD/MM/YYYY)
- *DueDate (DD/MM/YYYY)
- *ItemAmount
- *ItemTaxCode

## Features

- AI-powered extraction using Claude for accurate data parsing
- Supports multiple line items per invoice
- Automatic GST (5%) distribution across line items
- Automatic due date calculation (Net 30)
- Edit extracted data before export
- Preview CSV before download
