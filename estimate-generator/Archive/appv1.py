from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import subprocess
from datetime import datetime
import re
from weasyprint import HTML, CSS
import tempfile
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from io import BytesIO

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir() + '/uploads'
app.config['OUTPUT_FOLDER'] = tempfile.gettempdir() + '/outputs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Logo path - should be in the same directory as app.py or in static/
LOGO_PATH = None
for possible_path in ['logo.png', 'static/logo.png', os.path.join(os.path.dirname(__file__), 'logo.png'), os.path.join(os.path.dirname(__file__), 'static', 'logo.png')]:
    if os.path.exists(possible_path):
        LOGO_PATH = possible_path
        print(f"✅ Logo found: {os.path.abspath(possible_path)}")
        break

if not LOGO_PATH:
    print("⚠️  Logo not found - PDFs will be generated without logo")
    print("   Place logo.png in the same directory as app.py or in static/ folder")

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
    
    data_json = json.dumps(extracted_data, indent=2)
    
    formatting_prompt = f"""You are a professional document formatter specializing in painting estimates.

EXTRACTED DATA:
{data_json}

CALCULATED TOTALS:
- Subtotal: ${subtotal:,.2f}
- GST (5%): ${gst:,.2f}
- Total: ${total:,.2f}

Create a COMPLETE HTML estimate using this EXACT structure and design:

<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Professional Estimate</title>
    <style>
        /* Include ALL CSS inline */
    </style>
</head>
<body>

1. HEADER (Navy blue #2B4C7E background, white text, 30pt padding):
   
   CRITICAL - UPDATED HEADER FORMAT:
   - DO NOT include "ALL PAINTING LTD" text
   - DO NOT include "25 YEARS STRONG" text
   - Left side: Phone numbers ONLY in 11pt font (not 9pt):
     * (604) 330-1443
     * (604) 525-1403
   - Right side: Email in 11pt font (not 9pt):
     * info@allpaintingltd.ca
   - Leave space at top-left for logo (will be added later)
   
   EXACT HEADER TEMPLATE:
   ```
   <div style="background: #2B4C7E; color: white; padding: 30pt; position: relative;">
       <!-- Logo space reserved here - 120px x 90px at top-left -->
       <div style="position: absolute; top: 20pt; left: 20pt; width: 120px; height: 90px;"></div>
       
       <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 60pt;">
           <div style="font-size: 11pt; line-height: 1.8;">
               <div>(604) 330-1443</div>
               <div>(604) 525-1403</div>
           </div>
           <div style="font-size: 11pt; text-align: right;">
               info@allpaintingltd.ca
           </div>
       </div>
   </div>
   ```

2. CLIENT & PROJECT INFO (class="section"):
   - Two boxes side by side (class="info-box")
   - Navy blue headers (#2B4C7E, white text, 12pt)
   - Light gray backgrounds (#F8F9FA)
   - Client info left, Project info right
   - Content (11pt, line-height 1.6)

3. ESTIMATE DETAILS (class="section"):
   - Box with light blue background (#E3F2FD)
   - Estimate #, Date, Valid Until in bold (11pt)

4. SCOPE OF WORK SUMMARY (class="section"):
   - Header (14pt bold, color #2B4C7E)
   - Table (class="scope-table"):
     * Header row (Navy #2B4C7E, white text, 11pt)
     * Data rows (11pt, striped backgrounds)
     * Right-aligned amounts
   - Totals section (class="totals-section"):
     * Subtotal, GST, TOTAL
     * Larger font for TOTAL (14pt bold)

5. STANDARD INCLUSIONS (class="section"):
   - Header (12pt bold, color #2B4C7E)
   - Green checkmarks (✓) in color #28a745
   - Each item (11pt)

6. DETAILED SCOPE OF WORK (class="section"):
   - Header (14pt bold, color #2B4C7E)
   - Each scope subsection (class="no-break"):
     * Blue box (#E3F2FD, padding 15pt, border-left 4pt solid #2B4C7E)
     * Scope title (12pt bold, color #2B4C7E)
     * Bullet list (11pt, line-height 1.5)
     * Spacing between scopes (15pt)

7. EXCLUSIONS (class="section no-break"):
   
   EXACT CSS TEMPLATE:
   ```
   <div class="exclusions-section" style="page-break-inside: avoid; margin-bottom: 20pt;">
       <div style="background: #8B0000; color: white; font-size: 12pt; font-weight: bold; padding: 12pt; border-radius: 8px 8px 0 0;">
           EXCLUSIONS
       </div>
       <div style="border: 3px solid #8B0000; border-top: none; border-radius: 0 0 8px 8px; padding: 15pt; background: white;">
           <div style="font-size: 11pt; line-height: 1.6;">
               • Repair of structural damage or defects<br>
               • Electrical or plumbing modifications<br>
               • Removal or disposal of hazardous materials<br>
               • Window cleaning or replacement<br>
               • Landscaping or ground maintenance
           </div>
       </div>
   </div>
   ```

8. WARRANTY & CREDENTIALS (class="section no-break", 2 boxes side by side):
   
   EXACT CSS TEMPLATE:
   ```
   <div class="warranty-credentials-container" style="display: flex; gap: 15pt; page-break-inside: avoid;">
       <div class="warranty-box" style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; background: #F8F9FA; padding: 20pt; text-align: center;">
           <div style="font-size: 32pt; margin-bottom: 10pt;">🛡️</div>
           <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 8pt;">WARRANTY</div>
           <div style="font-size: 11pt; font-weight: bold; margin-bottom: 8pt;">2 YEAR WARRANTY</div>
           <div style="font-size: 11pt; line-height: 1.5;">All materials and workmanship are warranted for two (2) years from completion date. We stand behind our work and will address any warranty issues promptly at no additional cost.</div>
       </div>
       <div class="credentials-box" style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; background: #F8F9FA; padding: 20pt;">
           <div style="font-size: 32pt; margin-bottom: 10pt; text-align: center;">🏆</div>
           <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 8pt; text-align: center;">CREDENTIALS & CERTIFICATIONS</div>
           <div style="font-size: 11pt; line-height: 1.6; padding-left: 15pt;">
               • Licensed & Insured<br>
               • WCB Coverage<br>
               • Better Business Bureau Member<br>
               • Industry Certified Professionals<br>
               • Environmental Safety Certified
           </div>
       </div>
   </div>
   ```

9. PAYMENT TERMS (class="section no-break"):
   - Header (12pt bold, color #2B4C7E)
   - Bullet list (11pt)

10. SIGNATURE SECTION (class="section no-break"):
    - Header (12pt bold, color #2B4C7E)
    - 2 boxes side by side
    - Each: "Client Signature: _______ Date: _______" (11pt)

11. FOOTER (Navy #2B4C7E, white text):
    - Centered (10pt)
    - "ALL PAINTING LTD. | Your Full-Service Painting Company"
    - Contact info (9pt)

</body>
</html>

CRITICAL FORMATTING RULES:
1. CONSISTENT TYPOGRAPHY - Use exact font sizes specified above everywhere
2. NO PAGE BREAKS - Use page-break-inside: avoid on all sections
3. PROPER SPACING - Consistent margins and padding throughout
4. PROPER CAPITALIZATION - All sentences and bullets start with capital letters
5. ALL CSS INLINE - Include all styles in the HTML
6. PROFESSIONAL APPEARANCE - Clean, organized, easy to read
7. USE EXACT CSS TEMPLATES - For WARRANTY/CREDENTIALS and EXCLUSIONS sections, copy the CSS templates provided EXACTLY as shown
8. MATCH THE REFERENCE IMAGE - The design must match the format shown in the reference screenshot
9. UPDATED HEADER - Use 11pt font (not 9pt) for phone and email, remove company name and tagline

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

def add_logo_to_pdf(input_pdf_path, output_pdf_path, logo_path):
    """Add logo to the PDF header using PyPDF2 and ReportLab"""
    if not logo_path or not os.path.exists(logo_path):
        print("⚠️  Logo not found, skipping logo addition")
        # Just copy the file
        import shutil
        shutil.copy(input_pdf_path, output_pdf_path)
        return output_pdf_path
    
    try:
        # Read the existing PDF
        reader = PdfReader(input_pdf_path)
        writer = PdfWriter()
        
        # Create a new PDF with just the logo
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        
        # Logo positioning - top-left corner with white background
        # Letter size is 612 x 792 points
        # 0.5in margin = 36 points
        # Position logo at (36, 792 - 36 - logo_height)
        
        logo_width = 120  # pixels
        logo_height = 90  # pixels
        
        x_position = 36 + 20  # 0.5in margin + 20pt padding (matching header padding)
        y_position = 792 - 36 - 30 - logo_height  # From top: margin + header padding + logo height
        
        # Draw white rectangle as background for logo
        can.setFillColorRGB(1, 1, 1)  # White
        can.rect(x_position - 5, y_position - 5, logo_width + 10, logo_height + 10, fill=1, stroke=0)
        
        # Draw the logo
        img = ImageReader(logo_path)
        can.drawImage(img, x_position, y_position, width=logo_width, height=logo_height, preserveAspectRatio=True, mask='auto')
        
        can.save()
        
        # Move to the beginning of the BytesIO buffer
        packet.seek(0)
        logo_pdf = PdfReader(packet)
        
        # Merge logo with each page (typically just first page for header)
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            
            # Only add logo to first page (where header is)
            if page_num == 0:
                page.merge_page(logo_pdf.pages[0])
            
            writer.add_page(page)
        
        # Write the final PDF
        with open(output_pdf_path, 'wb') as output_file:
            writer.write(output_file)
        
        print(f"✅ Logo added successfully to PDF")
        return output_pdf_path
        
    except Exception as e:
        print(f"⚠️  Error adding logo: {e}")
        # If logo addition fails, just use the original PDF
        import shutil
        shutil.copy(input_pdf_path, output_pdf_path)
        return output_pdf_path

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
        temp_output_filename = f"temp_estimate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        temp_output_path = os.path.join(app.config['OUTPUT_FOLDER'], temp_output_filename)
        
        generate_pdf_from_html(html_content, temp_output_path)
        
        print(f"\n🎨 Step 5: Adding logo to PDF header...")
        output_filename = f"estimate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        add_logo_to_pdf(temp_output_path, output_path, LOGO_PATH)
        
        # Clean up temp file
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        
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
    print("Professional Format Edition with Logo Support")
    print("="*60)
    if LOGO_PATH:
        print(f"✅ Logo found: {os.path.abspath(LOGO_PATH)}")
    else:
        print("⚠️  Logo not found - place logo.png in app directory or static/ folder")
    print("Server starting on http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
