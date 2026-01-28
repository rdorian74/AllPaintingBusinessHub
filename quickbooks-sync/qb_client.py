"""
QuickBooks API Client
Handles creating invoices, finding customers, attaching PDFs
"""

import os
import json
import base64
import requests
from datetime import datetime
import config
from qb_auth import QBAuth


class QBClient:
    """QuickBooks Online API Client"""
    
    def __init__(self):
        self.auth = QBAuth()
        self.base_url = config.QBO_BASE_URL
        self.company_id = config.COMPANY_ID
    
    def _get_headers(self):
        """Get headers with current access token"""
        token = self.auth.get_access_token()
        if not token:
            raise Exception("Not authenticated. Please authorize the app first.")
        
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def _api_url(self, endpoint):
        """Build full API URL"""
        return f"{self.base_url}/v3/company/{self.company_id}/{endpoint}"
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """Make an API request with error handling"""
        url = self._api_url(endpoint)
        headers = self._get_headers()
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Check for auth errors
            if response.status_code == 401:
                # Try to refresh token and retry once
                print("🔄 Token expired, refreshing...")
                success, msg = self.auth.refresh_access_token()
                if success:
                    headers = self._get_headers()
                    if method == 'GET':
                        response = requests.get(url, headers=headers, params=params)
                    else:
                        response = requests.post(url, headers=headers, json=data)
                else:
                    raise Exception(f"Authentication failed: {msg}")
            
            return response
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {e}")
    
    # =========================================================================
    # CUSTOMER OPERATIONS
    # =========================================================================
    
    def find_customer_by_email(self, email):
        """Find a customer by email"""
        query = f"SELECT * FROM Customer WHERE PrimaryEmailAddr = '{email}'"
        
        response = self._make_request('GET', 'query', params={'query': query})
        
        if response.status_code == 200:
            data = response.json()
            customers = data.get('QueryResponse', {}).get('Customer', [])
            if customers:
                return customers[0]
        return None
    
    def _sanitize_customer_name(self, name):
        """Clean customer name for QuickBooks compatibility"""
        if not name:
            return "Unknown Customer"
        
        import re
        # Remove illegal characters (QuickBooks doesn't like colons, etc.)
        clean_name = re.sub(r'[:\*\?\"\<\>\|]', ' ', name)
        # Remove "Project:" or similar suffixes
        clean_name = re.sub(r'\s*Project\s*:.*$', '', clean_name, flags=re.IGNORECASE)
        # Collapse multiple spaces
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        # Truncate to 100 chars (QBO limit)
        return clean_name[:100] if clean_name else "Unknown Customer"
    
    def _extract_search_name(self, name):
        """Extract core company name for searching (first 2-3 significant words)"""
        if not name:
            return ""
        
        import re
        # First sanitize
        clean = self._sanitize_customer_name(name)
        
        # Remove common suffixes for searching
        clean = re.sub(r'\s+(Ltd\.?|Inc\.?|Corp\.?|LLC|Limited|Incorporated|Company|Co\.?)$', '', clean, flags=re.IGNORECASE)
        
        # Get first 2-3 words for search
        words = clean.split()
        if len(words) >= 2:
            return ' '.join(words[:2])  # "Steelhead Contracting"
        return clean
    
    def find_customer_by_name(self, company_name):
        """Find a customer by company/display name - tries multiple search strategies"""
        
        # Strategy 1: Try exact match first with sanitized name
        clean_name = self._sanitize_customer_name(company_name)
        safe_name = clean_name.replace("'", "\\'")
        query = f"SELECT * FROM Customer WHERE DisplayName = '{safe_name}'"
        
        response = self._make_request('GET', 'query', params={'query': query})
        if response.status_code == 200:
            customers = response.json().get('QueryResponse', {}).get('Customer', [])
            if customers:
                return customers[0]
        
        # Strategy 2: Try LIKE search with sanitized name
        query = f"SELECT * FROM Customer WHERE DisplayName LIKE '%{safe_name}%'"
        response = self._make_request('GET', 'query', params={'query': query})
        if response.status_code == 200:
            customers = response.json().get('QueryResponse', {}).get('Customer', [])
            if customers:
                return customers[0]
        
        # Strategy 3: Try with core name only (first 2 words)
        search_name = self._extract_search_name(company_name)
        if search_name and search_name != clean_name:
            safe_search = search_name.replace("'", "\\'")
            query = f"SELECT * FROM Customer WHERE DisplayName LIKE '%{safe_search}%'"
            response = self._make_request('GET', 'query', params={'query': query})
            if response.status_code == 200:
                customers = response.json().get('QueryResponse', {}).get('Customer', [])
                if customers:
                    print(f"   Found via partial match: '{search_name}'")
                    return customers[0]
        
        # Strategy 4: Try first word only (company name like "Steelhead")
        first_word = clean_name.split()[0] if clean_name else ""
        if first_word and len(first_word) > 3:
            safe_first = first_word.replace("'", "\\'")
            query = f"SELECT * FROM Customer WHERE DisplayName LIKE '{safe_first}%'"
            response = self._make_request('GET', 'query', params={'query': query})
            if response.status_code == 200:
                customers = response.json().get('QueryResponse', {}).get('Customer', [])
                if customers:
                    print(f"   Found via first word match: '{first_word}'")
                    return customers[0]
        
        return None
    
    def create_customer(self, company_name, contact_name=None, email=None, phone=None, address=None):
        """Create a new customer in QuickBooks"""
        
        # Sanitize the company name
        clean_company = self._sanitize_customer_name(company_name)
        
        customer_data = {
            'DisplayName': clean_company,
            'CompanyName': clean_company,
        }
        
        # Add contact name
        if contact_name:
            parts = contact_name.split(' ', 1)
            customer_data['GivenName'] = parts[0][:25] if parts else ''
            customer_data['FamilyName'] = parts[1][:25] if len(parts) > 1 else ''
        
        # Add email
        if email:
            customer_data['PrimaryEmailAddr'] = {'Address': email}
        
        # Add phone
        if phone:
            customer_data['PrimaryPhone'] = {'FreeFormNumber': phone}
        
        # Add billing address
        if address:
            # Try to parse address into components
            customer_data['BillAddr'] = {
                'Line1': address[:500]
            }
        
        response = self._make_request('POST', 'customer', data=customer_data)
        
        if response.status_code == 200:
            return response.json().get('Customer')
        else:
            error = response.json().get('Fault', {}).get('Error', [{}])[0]
            raise Exception(f"Failed to create customer: {error.get('Message', response.text)}")
    
    def find_or_create_customer(self, company_name, contact_name=None, email=None, phone=None, address=None):
        """Find existing customer or create new one"""
        
        # Try to find by company name first
        customer = self.find_customer_by_name(company_name)
        if customer:
            print(f"✅ Found existing customer: {customer['DisplayName']} (ID: {customer['Id']})")
            return customer
        
        # Try by email if provided
        if email:
            customer = self.find_customer_by_email(email)
            if customer:
                print(f"✅ Found customer by email: {customer['DisplayName']} (ID: {customer['Id']})")
                return customer
        
        # Create new customer
        print(f"📝 Creating new customer: {company_name}")
        customer = self.create_customer(company_name, contact_name, email, phone, address)
        print(f"✅ Created customer: {customer['DisplayName']} (ID: {customer['Id']})")
        return customer
    
    # =========================================================================
    # ITEM/SERVICE OPERATIONS
    # =========================================================================
    
    def find_item_by_name(self, item_name):
        """Find a service/product item by name"""
        safe_name = item_name.replace("'", "\\'")
        query = f"SELECT * FROM Item WHERE Name = '{safe_name}'"
        
        response = self._make_request('GET', 'query', params={'query': query})
        
        if response.status_code == 200:
            data = response.json()
            items = data.get('QueryResponse', {}).get('Item', [])
            if items:
                return items[0]
        return None
    
    def create_service_item(self, item_name):
        """Create a service item for invoice line items"""
        
        # First, get an income account
        query = "SELECT * FROM Account WHERE AccountType = 'Income' MAXRESULTS 1"
        response = self._make_request('GET', 'query', params={'query': query})
        
        income_account_id = None
        if response.status_code == 200:
            accounts = response.json().get('QueryResponse', {}).get('Account', [])
            if accounts:
                income_account_id = accounts[0]['Id']
        
        item_data = {
            'Name': item_name[:100],
            'Type': 'Service'
        }
        
        if income_account_id:
            item_data['IncomeAccountRef'] = {'value': income_account_id}
        
        response = self._make_request('POST', 'item', data=item_data)
        
        if response.status_code == 200:
            return response.json().get('Item')
        else:
            error = response.json().get('Fault', {}).get('Error', [{}])[0]
            raise Exception(f"Failed to create item: {error.get('Message', response.text)}")
    
    def find_or_create_item(self, item_name=None):
        """Find existing service item or create new one"""
        item_name = item_name or config.DEFAULT_ITEM_NAME
        
        item = self.find_item_by_name(item_name)
        if item:
            print(f"✅ Found existing item: {item['Name']} (ID: {item['Id']})")
            return item
        
        print(f"📝 Creating new item: {item_name}")
        item = self.create_service_item(item_name)
        print(f"✅ Created item: {item['Name']} (ID: {item['Id']})")
        return item
    
    # =========================================================================
    # INVOICE OPERATIONS
    # =========================================================================
    
    def create_invoice(self, customer_id, line_items, invoice_number=None, 
                       estimate_number=None, project_address=None, po_number=None,
                       due_date=None, memo=None):
        """
        Create an invoice in QuickBooks
        
        Args:
            customer_id: QuickBooks customer ID
            line_items: List of dicts with 'description' and 'amount'
            invoice_number: Your custom invoice number (e.g., '26C-004')
            estimate_number: Reference to estimate
            project_address: Project/ship-to address
            po_number: Purchase order number
            due_date: Due date string (YYYY-MM-DD)
            memo: Private memo
        """
        
        # Get or create the service item
        service_item = self.find_or_create_item()
        
        # Build line items
        qb_lines = []
        for idx, item in enumerate(line_items, 1):
            qb_lines.append({
                'DetailType': 'SalesItemLineDetail',
                'Amount': item.get('amount', 0),
                'Description': item.get('description', ''),
                'SalesItemLineDetail': {
                    'ItemRef': {'value': service_item['Id']},
                    'Qty': 1,
                    'UnitPrice': item.get('amount', 0)
                }
            })
        
        # Build invoice data
        invoice_data = {
            'CustomerRef': {'value': customer_id},
            'Line': qb_lines
        }
        
        # Add custom invoice number (DocNumber in QBO)
        if invoice_number:
            invoice_data['DocNumber'] = invoice_number
        
        # Add PO number
        if po_number:
            invoice_data['CustomField'] = [{
                'DefinitionId': '1',
                'StringValue': po_number,
                'Type': 'StringType',
                'Name': 'P.O. Number'
            }]
        
        # Add estimate reference in private note
        if estimate_number:
            invoice_data['PrivateNote'] = f"Estimate: {estimate_number}"
        
        # Add memo (customer memo)
        if memo:
            invoice_data['CustomerMemo'] = {'value': memo}
        
        # Add ship-to address (project address)
        if project_address:
            invoice_data['ShipAddr'] = {
                'Line1': project_address[:500]
            }
        
        # Add due date
        if due_date:
            invoice_data['DueDate'] = due_date
        
        # Make request
        response = self._make_request('POST', 'invoice', data=invoice_data)
        
        if response.status_code == 200:
            invoice = response.json().get('Invoice')
            print(f"✅ Invoice created: {invoice.get('DocNumber', invoice['Id'])}")
            return invoice
        else:
            error = response.json().get('Fault', {}).get('Error', [{}])[0]
            raise Exception(f"Failed to create invoice: {error.get('Message', response.text)}")
    
    # =========================================================================
    # ATTACHMENT OPERATIONS
    # =========================================================================
    
    def attach_pdf_to_invoice(self, invoice_id, pdf_path):
        """Attach a PDF file to an invoice"""
        
        if not os.path.exists(pdf_path):
            raise Exception(f"PDF file not found: {pdf_path}")
        
        # Read the PDF file
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        filename = os.path.basename(pdf_path)
        
        # QuickBooks attachments use multipart/form-data
        url = f"{self.base_url}/v3/company/{self.company_id}/upload"
        
        token = self.auth.get_access_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json'
        }
        
        # Metadata for the attachment
        metadata = {
            'AttachableRef': [{
                'EntityRef': {
                    'type': 'Invoice',
                    'value': str(invoice_id)
                }
            }],
            'FileName': filename,
            'ContentType': 'application/pdf'
        }
        
        files = {
            'file_metadata_01': (None, json.dumps(metadata), 'application/json'),
            'file_content_01': (filename, pdf_content, 'application/pdf')
        }
        
        try:
            response = requests.post(url, headers=headers, files=files)
            
            if response.status_code == 200:
                attachment = response.json().get('AttachableResponse', [{}])[0].get('Attachable')
                print(f"✅ PDF attached to invoice: {filename}")
                return attachment
            else:
                error_text = response.text
                try:
                    error = response.json().get('Fault', {}).get('Error', [{}])[0]
                    error_text = error.get('Message', response.text)
                except:
                    pass
                raise Exception(f"Failed to attach PDF: {error_text}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Attachment request failed: {e}")
    
    # =========================================================================
    # COMBINED OPERATIONS
    # =========================================================================
    
    def create_invoice_from_estimate(self, invoice_data, pdf_path=None):
        """
        Create a QuickBooks invoice from estimate data and optionally attach PDF
        
        Args:
            invoice_data: Dict with keys:
                - invoice_number: str (e.g., '26C-004')
                - estimate_number: str (e.g., '25C-326')
                - client_company: str
                - client_contact: str
                - client_email: str
                - client_phone: str
                - client_address: str
                - project_address: str
                - po_number: str
                - line_items: list of {'description': str, 'amount': float}
                - subtotal: float
            pdf_path: Path to PDF invoice to attach (optional)
        
        Returns:
            Dict with invoice details and QBO link
        """
        
        print("\n" + "="*60)
        print("CREATING QUICKBOOKS INVOICE")
        print("="*60)
        
        # Step 1: Find or create customer
        print("\n📋 Step 1: Finding/creating customer...")
        customer = self.find_or_create_customer(
            company_name=invoice_data.get('client_company') or invoice_data.get('client_contact', 'Unknown'),
            contact_name=invoice_data.get('client_contact'),
            email=invoice_data.get('client_email'),
            phone=invoice_data.get('client_phone'),
            address=invoice_data.get('client_address')
        )
        
        # Step 2: Prepare line items
        print("\n📋 Step 2: Preparing line items...")
        line_items = invoice_data.get('line_items', [])
        if not line_items:
            # Create single line item from subtotal
            line_items = [{
                'description': invoice_data.get('project_name', 'Painting Services'),
                'amount': invoice_data.get('subtotal', 0)
            }]
        
        # Step 3: Create invoice
        print("\n📋 Step 3: Creating invoice...")
        invoice = self.create_invoice(
            customer_id=customer['Id'],
            line_items=line_items,
            invoice_number=invoice_data.get('invoice_number'),
            estimate_number=invoice_data.get('estimate_number'),
            project_address=invoice_data.get('project_address'),
            po_number=invoice_data.get('po_number')
        )
        
        # Step 4: Attach PDF if provided
        attachment = None
        if pdf_path and os.path.exists(pdf_path):
            print(f"\n📋 Step 4: Attaching PDF...")
            try:
                attachment = self.attach_pdf_to_invoice(invoice['Id'], pdf_path)
            except Exception as e:
                print(f"⚠️ Warning: Could not attach PDF: {e}")
        
        # Build QuickBooks invoice URL
        if config.USE_SANDBOX:
            qb_url = f"https://app.sandbox.qbo.intuit.com/app/invoice?txnId={invoice['Id']}"
        else:
            qb_url = f"https://app.qbo.intuit.com/app/invoice?txnId={invoice['Id']}"
        
        print("\n" + "="*60)
        print("✅ QUICKBOOKS INVOICE CREATED SUCCESSFULLY!")
        print(f"   Invoice #: {invoice.get('DocNumber', invoice['Id'])}")
        print(f"   QBO Link: {qb_url}")
        print("="*60 + "\n")
        
        return {
            'success': True,
            'qb_invoice_id': invoice['Id'],
            'qb_invoice_number': invoice.get('DocNumber'),
            'qb_customer_id': customer['Id'],
            'qb_customer_name': customer['DisplayName'],
            'qb_url': qb_url,
            'pdf_attached': attachment is not None,
            'total': invoice.get('TotalAmt', 0)
        }
    
    def get_invoice(self, invoice_id):
        """Get invoice details by ID"""
        response = self._make_request('GET', f'invoice/{invoice_id}')
        
        if response.status_code == 200:
            return response.json().get('Invoice')
        return None
    
    def test_connection(self):
        """Test the API connection"""
        try:
            query = "SELECT * FROM CompanyInfo"
            response = self._make_request('GET', 'query', params={'query': query})
            
            if response.status_code == 200:
                company = response.json().get('QueryResponse', {}).get('CompanyInfo', [{}])[0]
                return {
                    'success': True,
                    'company_name': company.get('CompanyName'),
                    'country': company.get('Country'),
                    'message': f"Connected to: {company.get('CompanyName')}"
                }
            else:
                return {
                    'success': False,
                    'message': f"API error: {response.status_code}"
                }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }
