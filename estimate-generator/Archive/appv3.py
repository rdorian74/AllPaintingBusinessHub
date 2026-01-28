from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import subprocess
from datetime import datetime
import re
from weasyprint import HTML, CSS
import tempfile

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir() + '/uploads'
app.config['OUTPUT_FOLDER'] = tempfile.gettempdir() + '/outputs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

def safe_float(value, default=0.0):
    """Safely convert a value to float"""
    if value is None or value == '':
        return default
    try:
        if isinstance(value, str):
            value = value.replace('$', '').replace(',', '').strip()
        return float(value)
    except (ValueError, TypeError):
        return default

def extract_text_from_doc(file_path):
    """Extract text from .doc or .docx files"""
    text = ""
    
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = '\n'.join(paragraphs)
        if text and len(text) > 100:
            print(f"✅ Extracted {len(text)} characters using python-docx")
            return text
    except Exception as e:
        print(f"python-docx failed: {e}")
    
    try:
        import docx2txt
        text = docx2txt.process(file_path)
        if text and len(text) > 100:
            print(f"✅ Extracted {len(text)} characters using docx2txt")
            return text
    except Exception as e:
        print(f"docx2txt failed: {e}")
    
    try:
        result = subprocess.run(['antiword', file_path], capture_output=True, text=True, check=True)
        text = result.stdout
        if text and len(text) > 100:
            print(f"✅ Extracted {len(text)} characters using antiword")
            return text
    except Exception as e:
        print(f"antiword failed: {e}")
    
    return text if text else "Error: Could not extract text from document"

def call_claude_for_extraction(document_text):
    """Use Claude AI to extract structured data from the document"""
    import anthropic
    
    client = anthropic.Anthropic()
    
    extraction_prompt = f"""You are an expert at extracting information from painting estimate documents. 

DOCUMENT TEXT:
{document_text}

Extract ALL information and return it as JSON. Be VERY thorough - extract every detail.

CRITICAL RULES:
1. Extract ALL dollar amounts - look for patterns like $27,746.14 or 27746.14
2. Extract ALL scope items (Interior Painting, Exterior Painting, etc.)
3. For amounts, return ONLY the number without $ or commas (example: "27746.14" not "$27,746.14")
4. If you cannot find a value, use an empty string "" not null
5. Extract the complete estimate number (like "25C-285-A" or "OUR ESTIMATE # 25C-285-A")
6. Extract the complete client name and company
7. Extract ALL painting specifications and details
8. GRAMMAR & SPELLING: Fix any grammar or spelling errors in the extracted text, BUT preserve the original meaning and technical content
9. Capitalize the first letter of every sentence and bullet point
10. Ensure proper punctuation throughout
11. ADDENDUM EXTRACTION: Look for text like "Addendum 1", "Addendum 2", "Addendum #3", etc. Extract the highest addendum number found. If NO addendum is found, return "No addendums"
12. REVISED EXTRACTION: Look for text like "Revised 1", "Revised 2", "Revision 3", etc. Extract the revision information if found

SMART CONTACT EXTRACTION RULES:
13. PHONE NUMBER: Look for patterns like (604) 123-4567, 604-123-4567, 604.123.4567, or 6041234567. Also look after keywords: "Phone:", "Tel:", "Cell:", "Mobile:". Extract the COMPLETE phone number.
14. EMAIL: Look for text with @ symbol. Also look after keywords: "Email:", "E-mail:", "Mail:". Extract the COMPLETE email address.
15. CONTACT PERSON: Look for text after "Attention:", "Attn:", "Contact:", "For:", or first person name mentioned near address. If not found but company name exists, leave empty.
16. COMPANY NAME: Look for business names, company names, or organization names. If no company name found but contact person exists, use contact person name as company name.
17. ADDRESS COMBINATION: Build complete addresses intelligently by combining street, city, province, and postal code fields. Ensure proper formatting with commas.

Return ONLY this JSON structure with NO markdown formatting, NO backticks:

{{
    "client_info": {{
        "company_name": "",
        "contact_person": "",
        "address": "",
        "city_province_postal": "",
        "phone": "",
        "email": ""
    }},
    "project_info": {{
        "name": "",
        "address": "",
        "city_province_postal": ""
    }},
    "estimate_number": "",
    "date": "",
    "addendum_count": "",
    "revised": "",
    "scopes": [
        {{
            "scope_number": "1",
            "title": "Interior Painting",
            "description": "Brief summary of interior work",
            "amount": "27746.14"
        }},
        {{
            "scope_number": "2",
            "title": "Exterior Painting", 
            "description": "Brief summary of exterior work",
            "amount": "6560.56"
        }}
    ],
    "scope_details": [
        {{
            "scope_id": "1",
            "scope_title": "INTERIOR PAINTING",
            "items": [
                "List every single painting specification here - WITH PROPER CAPITALIZATION",
                "Include primer types, paint types, colors, surfaces",
                "Each item should start with a capital letter and have proper grammar"
            ]
        }},
        {{
            "scope_id": "2",
            "scope_title": "EXTERIOR PAINTING",
            "items": [
                "List exterior specifications with proper grammar and capitalization"
            ]
        }}
    ],
    "important_notes": [
        "Extract ALL notes with proper capitalization and grammar",
        "Each bullet point should be a complete, properly formatted sentence"
    ],
    "standard_inclusions": [
        "Ladding and lifting supplies as painted areas",
        "Protection of all non-painted areas",
        "Extract ALL inclusions with proper grammar"
    ],
    "exclusions": [
        "GST (Goods and Services Tax @ 5%)",
        "Extract ALL exclusions with proper capitalization"
    ],
    "warranty_info": {{
        "years": "2",
        "description": "Two Year Limited Warranty on Material and Workmanship"
    }},
    "credentials": [
        "Five Million Liability Insurance",
        "WCB Coverage",
        "Better Business Bureau Member"
    ],
    "payment_terms": [
        "Progress payments as necessary",
        "Payment on completion"
    ],
    "validity_days": "30"
}}

REMEMBER: 
- Return PURE JSON only. No ```json or ``` markers
- Extract EVERYTHING from the document
- Fix grammar and spelling while preserving meaning
- Capitalize properly
- Make it professional"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": extraction_prompt}]
    )
    
    response_text = message.content[0].text.strip()
    response_text = re.sub(r'^```json\s*', '', response_text)
    response_text = re.sub(r'^```\s*', '', response_text)
    response_text = re.sub(r'\s*```$', '', response_text)
    response_text = response_text.strip()
    
    try:
        data = json.loads(response_text)
        
        if 'scopes' in data:
            for scope in data['scopes']:
                if 'amount' in scope:
                    amount_str = str(scope['amount']).replace('$', '').replace(',', '').strip()
                    scope['amount'] = amount_str if amount_str else "0"
        
        print("✅ Successfully extracted data")
        print(f"Found {len(data.get('scopes', []))} scopes")
        return data
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        print(f"Response (first 500 chars): {response_text[:500]}")
        raise

def call_claude_for_formatting(extracted_data):
    """Use Claude AI to create a professional HTML estimate"""
    import anthropic
    
    client = anthropic.Anthropic()
    
    scopes = extracted_data.get('scopes', [])
    subtotal = sum(safe_float(scope.get('amount', 0)) for scope in scopes)
    gst = subtotal * 0.05
    total = subtotal + gst
    
    print(f"💰 Calculated totals - Subtotal: ${subtotal:,.2f}, GST: ${gst:,.2f}, Total: ${total:,.2f}")
    
    if not extracted_data.get('date'):
        extracted_data['date'] = datetime.now().strftime('%B %d, %Y')
    
    formatting_prompt = f"""Create a professional HTML estimate document with PERFECT formatting.

DATA:
{json.dumps(extracted_data, indent=2)}

TOTALS:
Subtotal: ${subtotal:,.2f}
GST (5%): ${gst:,.2f}
Total: ${total:,.2f}

TYPOGRAPHY STANDARDS (USE EVERYWHERE):
- Font Family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif
- Body Text: 11pt
- Headings (H1): 18pt bold
- Headings (H2): 14pt bold  
- Section Headers: 12pt bold
- Table Headers: 11pt bold
- Small Text (footer, labels): 9pt
- Line Height: 1.5 for body text, 1.3 for headers
- Color: #333333 for body text, #2B4C7E for navy elements

CRITICAL PAGE BREAK CONTROL:
- EVERY major section MUST have: page-break-inside: avoid !important; AND break-inside: avoid !important;
- Use BOTH properties for maximum compatibility
- Never allow sections to be split across pages
- Keep headers with their content using page-break-after: avoid !important;
- Tables must have page-break-inside: avoid !important;

DESIGN SPECIFICATION:

<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: letter;
            margin: 0.5in 0.5in 1.2in 0.5in;
            @bottom-center {{
                content: element(footer);
            }}
            @bottom-right {{
                content: "Page " counter(page);
                font-size: 10pt;
                color: #666;
            }}
        }}
        
        #footer {{
            position: running(footer);
            width: 100%;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.5;
            color: #333333;
        }}
        
        .no-break {{
            page-break-inside: avoid !important;
            break-inside: avoid !important;
        }}
        
        h1 {{
            font-size: 18pt;
            font-weight: bold;
            margin-bottom: 10pt;
            page-break-after: avoid !important;
        }}
        
        h2 {{
            font-size: 14pt;
            font-weight: bold;
            margin-bottom: 8pt;
            page-break-after: avoid !important;
        }}
        
        .section {{
            page-break-inside: avoid !important;
            break-inside: avoid !important;
            margin-bottom: 20pt;
        }}
        
        table {{
            page-break-inside: avoid !important;
        }}
        
        ul, ol {{
            padding-left: 25pt !important;
            list-style-position: outside;
        }}
        
        li {{
            padding-left: 5pt;
            margin-bottom: 6pt;
        }}
    </style>
</head>
<body>

1. HEADER (Navy #2B4C7E, white text, padding 25pt, ROUNDED CORNERS border-radius: 10px, page-break-inside: avoid !important):
   LEFT:
   - "ALL PAINTING LTD." (20pt bold)
   - "Your Full-Service Painting Company" (10pt)
   
   RIGHT:
   - "ESTIMATE" (18pt bold)
   - "Estimate #: {extracted_data.get('estimate_number', 'TBD')}" (11pt)
   - "Date: {extracted_data.get('date', '')}" (11pt)
   - "Addendum {extracted_data.get('addendum_count', 'No addendums')}" (11pt)
   - IF revised field exists and is not empty: "Revised: {extracted_data.get('revised', '')}" (11pt)
   - "Valid for: {extracted_data.get('validity_days', '30')} days" (11pt)
   
   BOTTOM (centered, 11pt):
   - Phone: (604) 330-1443 & (604) 525-1403 | Email: info@allpaintingltd.ca | Website: www.allpaintingltd.ca

SMART CONTACT EXTRACTION RULES (use throughout document):
- Look for phone patterns: (604) 123-4567, 604-123-4567, 604.123.4567, or 6041234567
- Look for email with @ symbol anywhere in document
- If contact person missing, look for "Attention:", "Attn:", "Contact:", or first name found
- If company name empty, use contact person name
- Build addresses intelligently: [street], [city], [province] [postal]

2. CLIENT & PROJECT INFO (class="section no-break", 2 columns, ROUNDED CORNER BOXES border-radius: 10px, page-break-inside: avoid !important):
   
   LEFT COLUMN (border: 3px solid #2B4C7E; border-radius: 10px; padding: 20pt):
   - "CLIENT INFORMATION" (12pt bold, color #2B4C7E, with bottom border)
   - Company: {extracted_data.get('client_info', {}).get('company_name', '') or 'contact person as fallback'} (11pt)
   - Contact: ... (11pt each line)
   - Address: [use smart combining of address fields] (11pt)
   - Phone: [smart phone extraction] (11pt)
   - Email: [smart email extraction] (11pt)
   
   RIGHT COLUMN (border: 3px solid #2B4C7E; border-radius: 10px; padding: 20pt):
   - "PROJECT LOCATION" (12pt bold, color #2B4C7E, with bottom border)
   - Project: ... (11pt each line)
   - Address: [smart combined project address] (11pt)

3. EXECUTIVE SUMMARY (class="section no-break", page-break-inside: avoid !important):
   - "EXECUTIVE SUMMARY" header (14pt bold, color #2B4C7E)
   - Table with borders (page-break-inside: avoid !important)
   - Header row: Scope | Description | Amount (11pt bold, background #F5F5F5)
   - Data rows (11pt)
   - Right-align amounts
   - SUBTOTAL (navy #2B4C7E, white 11pt bold): ${subtotal:,.2f}
   - GST (5%) (11pt): ${gst:,.2f}
   - TOTAL (navy #2B4C7E, white 12pt bold): ${total:,.2f}

4. GENERAL TERMS & CONDITIONS (class="section no-break", page-break-inside: avoid !important; break-inside: avoid !important):
   
   EXACT CSS TEMPLATE:
   ```
   <div class="terms-section" style="page-break-inside: avoid !important; break-inside: avoid !important; margin-bottom: 20pt;">
       <div style="background: #8B0000; color: white; font-size: 12pt; font-weight: bold; padding: 12pt; border-radius: 8px 8px 0 0; page-break-after: avoid !important;">
           GENERAL TERMS & CONDITIONS
       </div>
       <div style="border: 3px solid #F0E68C; border-top: none; border-radius: 0 0 8px 8px; padding: 15pt; background: #FFF9E6;">
           <ul style="margin: 0; padding-left: 25pt !important; list-style-type: disc; line-height: 1.6; list-style-position: outside;">
               <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">Item 1</li>
               <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">Item 2</li>
           </ul>
       </div>
   </div>
   ```

5. STANDARD INCLUSIONS (class="section no-break", page-break-inside: avoid !important; break-inside: avoid !important):
   
   EXACT CSS TEMPLATE:
   ```
   <div class="inclusions-section" style="page-break-inside: avoid !important; break-inside: avoid !important; margin-bottom: 20pt;">
       <div style="background: #2B4C7E; color: white; font-size: 12pt; font-weight: bold; padding: 12pt; border-radius: 8px 8px 0 0; page-break-after: avoid !important;">
           STANDARD INCLUSIONS
       </div>
       <div style="border: 3px solid #2B4C7E; border-top: none; border-radius: 0 0 8px 8px; padding: 15pt; background: white;">
           <div style="font-size: 11pt; line-height: 1.6; column-count: 2; column-gap: 20pt;">
               <ul style="margin: 0; padding-left: 25pt !important; list-style-position: outside;">
                   <li style="padding-left: 5pt; margin-bottom: 6pt;"><span style="color: #28a745;">✓</span> Item 1</li>
                   <li style="padding-left: 5pt; margin-bottom: 6pt;"><span style="color: #28a745;">✓</span> Item 2</li>
               </ul>
           </div>
       </div>
   </div>
   ```

6. DETAILED SCOPE OF WORK (class="section"):
   - Main header "DETAILED SCOPE OF WORK" (14pt bold, color #2B4C7E, page-break-after: avoid !important) at the top
   - Then for EACH item in extracted_data['scope_details'], create a subsection using EXACT CSS TEMPLATE below:
   
   CRITICAL: Use ALL items from scope_details array. Each scope_detail item has: scope_id, scope_title, and items array.
   
   EXACT CSS TEMPLATE for each scope_detail:
   ```
   <div class="scope-detail-section" style="page-break-inside: avoid !important; break-inside: avoid !important; margin-bottom: 20pt;">
       <div style="background: #2B4C7E; color: white; font-size: 12pt; font-weight: bold; padding: 12pt; border-radius: 8px 8px 0 0; page-break-after: avoid !important;">
           {{scope_detail.scope_title}}
       </div>
       <div style="border: 3px solid #2B4C7E; border-top: none; border-radius: 0 0 8px 8px; padding: 15pt; background: white;">
           <ul style="margin: 0; padding-left: 25pt !important; list-style-type: disc; line-height: 1.6; list-style-position: outside;">
               <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">{{item 1}}</li>
               <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">{{item 2}}</li>
           </ul>
       </div>
   </div>
   ```
   
   CRITICAL: Wrap entire scope section (header + content box) in page-break-inside: avoid !important; and break-inside: avoid !important;

7. EXCLUSIONS (class="section no-break", page-break-inside: avoid !important; break-inside: avoid !important):
   
   EXACT CSS TEMPLATE (use 2 columns if more than 5 items):
   ```
   <div class="exclusions-section" style="page-break-inside: avoid !important; break-inside: avoid !important; margin-bottom: 20pt;">
       <div style="background: #8B0000; color: white; font-size: 12pt; font-weight: bold; padding: 12pt; border-radius: 8px 8px 0 0; page-break-after: avoid !important;">
           EXCLUSIONS
       </div>
       <div style="border: 3px solid #8B0000; border-top: none; border-radius: 0 0 8px 8px; padding: 15pt; background: white;">
           <div style="font-size: 11pt; line-height: 1.6; column-count: 2; column-gap: 20pt;">
               <ul style="margin: 0; padding-left: 25pt !important; list-style-position: outside;">
                   <li style="padding-left: 5pt; margin-bottom: 6pt;">Item 1</li>
                   <li style="padding-left: 5pt; margin-bottom: 6pt;">Item 2</li>
               </ul>
           </div>
       </div>
   </div>
   ```
   NOTE: If there are 5 or fewer exclusions, use column-count: 1. If more than 5, use column-count: 2.

8. WARRANTY & CREDENTIALS (class="section no-break", 2 boxes side by side, page-break-inside: avoid !important):
   
   EXACT CSS TEMPLATE:
   ```
   <div class="warranty-credentials-container" style="display: flex; gap: 15pt; page-break-inside: avoid !important; break-inside: avoid !important;">
       <div class="warranty-box" style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; background: #F8F9FA; padding: 20pt; text-align: center;">
           <div style="font-size: 32pt; margin-bottom: 10pt;">🛡️</div>
           <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 8pt;">WARRANTY</div>
           <div style="font-size: 11pt; font-weight: bold; margin-bottom: 8pt;">2 YEAR WARRANTY</div>
           <div style="font-size: 11pt; line-height: 1.5;">All materials and workmanship are warranted for two (2) years from completion date. We stand behind our work and will address any warranty issues promptly at no additional cost.</div>
       </div>
       <div class="credentials-box" style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; background: #F8F9FA; padding: 20pt;">
           <div style="font-size: 32pt; margin-bottom: 10pt; text-align: center;">🏆</div>
           <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 8pt; text-align: center;">CREDENTIALS & CERTIFICATIONS</div>
           <ul style="margin: 0; padding-left: 25pt !important; list-style-type: disc; line-height: 1.6; list-style-position: outside;">
               <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">Licensed & Insured</li>
               <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">WCB Coverage</li>
               <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">Better Business Bureau Member</li>
           </ul>
       </div>
   </div>
   ```

9. PAYMENT TERMS (class="section no-break", page-break-inside: avoid !important):
   - Header (12pt bold, color #2B4C7E, page-break-after: avoid !important)
   - <ul style="padding-left: 25pt !important; list-style-position: outside;">
   - <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 6pt;">Payment term</li>

10. SIGNATURE SECTION (class="section no-break", page-break-inside: avoid !important):
    - Header (12pt bold, color #2B4C7E)
    - 2 boxes side by side (border-radius: 5px)
    - Each: "Client Signature: _______ Date: _______" (11pt)

11. FOOTER (Simple line with company info, appears on EVERY page):
    
    EXACT CSS TEMPLATE (this footer will appear automatically on every page):
    ```
    <div id="footer">
        <div style="border-top: 2px solid #2B4C7E; padding-top: 10pt; text-align: center; font-size: 10pt; color: #333;">
            ALL PAINTING LTD | Phone: (604) 330-1443 & (604) 525-1403 | www.allpaintingltd.ca
        </div>
    </div>
    ```
    NOTE: Place this div at the very beginning of the body, right after opening <body> tag. The CSS @page rule will make it appear on every page automatically.

</body>
</html>

CRITICAL FORMATTING RULES:
1. CONSISTENT TYPOGRAPHY - Use exact font sizes specified above everywhere
2. STRICT PAGE BREAKS - EVERY section MUST have BOTH: page-break-inside: avoid !important; AND break-inside: avoid !important;
3. ROUNDED CORNERS - Header MUST have border-radius: 10px, Client/Project boxes MUST have border-radius: 10px
4. PROPER SPACING - Consistent margins (20pt between sections) and padding throughout
5. PROPER CAPITALIZATION - All sentences and bullets start with capital letters
6. ALL CSS INLINE - Include all styles in the HTML
7. PROFESSIONAL APPEARANCE - Clean, organized, easy to read
8. USE EXACT CSS TEMPLATES - Copy the CSS templates provided EXACTLY as shown
9. BULLET POINT INDENTATION - CRITICAL: ALL <ul> tags MUST have padding-left: 25pt !important; list-style-position: outside; ALL <li> tags MUST have padding-left: 5pt; margin-bottom: 6pt;
10. FOOTER PLACEMENT - Place the footer div (with id="footer") at the VERY BEGINNING of the body tag, right after <body>
11. PAGE NUMBERING - The CSS automatically adds page numbers in the bottom right of each page
12. SMART CONTACT EXTRACTION - Parse phone/email intelligently throughout document, handle missing fields gracefully

Return ONLY the complete HTML. No markdown, no code blocks, no explanations."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        messages=[{"role": "user", "content": formatting_prompt}]
    )
    
    html_content = message.content[0].text.strip()
    html_content = re.sub(r'^```html\s*', '', html_content)
    html_content = re.sub(r'^```\s*', '', html_content)
    html_content = re.sub(r'\s*```$', '', html_content)
    
    print("✅ HTML generated successfully")
    return html_content

def generate_pdf_from_html(html_content, output_path):
    """Convert HTML to PDF using WeasyPrint with proper page settings"""
    # Add additional CSS for better page control
    extra_css = CSS(string='''
        @page {
            size: letter;
            margin: 0.5in;
        }
        .no-break, .section {
            page-break-inside: avoid !important;
        }
        table {
            page-break-inside: avoid !important;
        }
    ''')
    
    HTML(string=html_content).write_pdf(output_path, stylesheets=[extra_css])
    return output_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith(('.doc', '.docx')):
        return jsonify({'error': 'Only .doc and .docx files are supported'}), 400
    
    try:
        filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(file.filename)[1]}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'message': 'Document uploaded successfully'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process/<filename>', methods=['POST'])
def process_document(filename):
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404
        
        print("\n" + "="*60)
        print("STARTING DOCUMENT PROCESSING")
        print("="*60)
        
        print(f"\n📄 Step 1: Extracting text from {filename}...")
        document_text = extract_text_from_doc(filepath)
        
        if not document_text or len(document_text) < 100:
            return jsonify({'error': 'Could not extract sufficient text from document. Please ensure it is a valid Word document.'}), 500
        
        print(f"✅ Extracted {len(document_text)} characters")
        
        print(f"\n🤖 Step 2: Using Claude AI to extract and polish data...")
        extracted_data = call_claude_for_extraction(document_text)
        
        print(f"\n🎨 Step 3: Generating professionally formatted HTML...")
        html_content = call_claude_for_formatting(extracted_data)
        
        print(f"\n📑 Step 4: Converting to PDF with page break control...")
        # Use the same name as the input file but with .pdf extension
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        # Remove the "upload_YYYYMMDD_HHMMSS" prefix if it exists
        if base_name.startswith('upload_'):
            base_name = '_'.join(base_name.split('_')[3:]) if len(base_name.split('_')) > 3 else base_name
        output_filename = f"{base_name}.pdf" if base_name else f"estimate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        generate_pdf_from_html(html_content, output_path)
        
        print(f"✅ PDF generated: {output_filename}")
        print("="*60)
        print("PROCESSING COMPLETE!")
        print("="*60 + "\n")
        
        return jsonify({
            'success': True,
            'pdf_filename': output_filename,
            'extracted_data': extracted_data,
            'message': 'Document processed successfully'
        })
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n❌ ERROR:\n{error_trace}")
        return jsonify({'error': f'{str(e)}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(filepath, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    print("\n" + "="*60)
    print("ALL PAINTING LTD - ESTIMATE GENERATOR")
    print("Professional Format Edition")
    print("="*60)
    print("Server starting on http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
