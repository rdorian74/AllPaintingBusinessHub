from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
import os
import json
import subprocess
from datetime import datetime
import re
from weasyprint import HTML, CSS
import tempfile

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir() + '/uploads'
app.config['OUTPUT_FOLDER'] = tempfile.gettempdir() + '/outputs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Check if logo exists
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'logo.png')
HAS_LOGO = os.path.exists(LOGO_PATH)

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
13. PHONE NUMBER: Look for ALL phone patterns like (604) 123-4567, 604-123-4567, 604.123.4567, or 6041234567. Also look after keywords: "Phone:", "Tel:", "Cell:", "Mobile:". Extract ALL phone numbers found, separated by " / " if multiple.
14. EMAIL: Look for ALL text with @ symbol. Also look after keywords: "Email:", "E-mail:", "Mail:". Extract ALL email addresses found, separated by " / " if multiple. IMPORTANT: Extract the company name from the email domain if no explicit company name is found (e.g., richard@titanconstruction.net means company is likely "Titan Construction").
15. CONTACT PERSON: Look for text after "Attention:", "Attn:", "Contact:", "For:", or person names mentioned. Extract ALL contact persons found, separated by " / " if multiple. This is the PERSON'S NAME, not the company.
16. COMPANY NAME: CRITICAL - This must be the BUSINESS/ORGANIZATION name, NOT the contact person's name. Look for: business names ending in Ltd, Inc, Corp, LLC, Construction, Contracting, Development, etc. Check the email domain for company hints. If truly no company name found, ONLY then use contact person name.
17. ADDRESS COMBINATION: Build complete addresses intelligently by combining street, city, province, and postal code fields. Ensure proper formatting with commas. Extract the CLIENT'S address (company address), not just the project address.

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
        "MPI inspection and MPI warranty not included",
        "Painting of any other areas not listed",
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
    
    print(f"💰 Calculated subtotal: ${subtotal:,.2f}")
    
    if not extracted_data.get('date'):
        extracted_data['date'] = datetime.now().strftime('%B %d, %Y')
    
    # Prepare logo tag for header - with address and contact info
    logo_html = ""
    if HAS_LOGO:
        logo_html = f'<div><img src="file://{LOGO_PATH}" style="height: 90px; width: auto; display: block; margin-bottom: 5pt;"><div style="font-size: 9pt; color: #555; line-height: 1.4;">Unit 1001, 115 Schoolhouse St, Coquitlam, BC, V3K 4X8<br>Phone: (604) 525-1403 | Email: info@allpaintingltd.ca<br>www.allpaintingltd.ca</div></div>'
        print(f"✅ Logo will be included from: {LOGO_PATH}")
    else:
        logo_html = '<div><div style="font-size: 22pt; font-weight: bold; color: #2B4C7E;">ALL PAINTING LTD.</div><div style="font-size: 10pt; color: #555;">Your Full-Service Painting Company</div><div style="font-size: 9pt; color: #555; margin-top: 5pt; line-height: 1.4;">Unit 1001, 115 Schoolhouse St, Coquitlam, BC, V3K 4X8<br>Phone: (604) 525-1403 | Email: info@allpaintingltd.ca<br>www.allpaintingltd.ca</div></div>'
        print("⚠️  No logo - using text fallback")
    
    formatting_prompt = f"""Create a professional HTML estimate document with PERFECT formatting.

⚠️ CRITICAL HTML REQUIREMENTS - READ FIRST:
1. Use ONLY inline styles (style="...") - NO external CSS classes
2. Use proper HTML <div>, <table>, <ul>, <li> tags - NOT bullet characters •
3. COPY the exact HTML templates provided - do not simplify or modify them
4. border-radius MUST be included on all rounded elements
5. All styles MUST be inline within the HTML tags

DATA:
{json.dumps(extracted_data, indent=2)}

TOTALS:
Subtotal: ${subtotal:,.2f}

NOTE: GST is EXCLUDED from this estimate. Show only SUBTOTAL in Executive Summary (no GST row, no Total row).

TYPOGRAPHY STANDARDS (USE EVERYWHERE):
- Font Family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif
- Body Text: 11pt
- Headings (H1): 18pt bold
- Headings (H2): 14pt bold  
- Section Headers: 12pt bold
- Table Headers: 11pt bold
- Small Text (footer, labels): 9pt
- Line Height: 1.35 for body text, 1.2 for headers
- Color: #333333 for body text, #2B4C7E for navy elements

SMART PAGE BREAK CONTROL (OPTION 3 - HYBRID):
- SHORT sections (Client Info, Warranty, Payment Terms): NEVER break - use page-break-inside: avoid !important;
- LONG sections (Detailed Scope with many bullets): ALLOW breaks but keep header with first few items
- Headers: ALWAYS keep with content using page-break-after: avoid !important; and orphans: 3;
- Reduce spacing: margin-bottom: 15pt (instead of 20pt) for better space utilization
- Tables: page-break-inside: avoid !important;

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
            line-height: 1.35;
            color: #333333;
        }}
        
        .no-break {{
            page-break-inside: avoid !important;
            break-inside: avoid !important;
        }}
        
        h1 {{
            font-size: 18pt;
            font-weight: bold;
            margin-bottom: 8pt;
            page-break-after: avoid !important;
            orphans: 3;
            widows: 3;
        }}
        
        h2 {{
            font-size: 14pt;
            font-weight: bold;
            margin-bottom: 8pt;
            page-break-after: avoid !important;
            orphans: 3;
            widows: 3;
        }}
        
        .section {{
            margin-bottom: 12pt;
        }}
        
        .section-header {{
            page-break-after: avoid !important;
            orphans: 3;
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
            margin-bottom: 3pt;
            orphans: 2;
            widows: 2;
        }}
    </style>
</head>
<body>

1. HEADER - COPY THIS EXACT TEMPLATE:

```html
<div style="margin-bottom: 12pt; page-break-inside: avoid !important; border-bottom: 3px solid #2B4C7E; padding-bottom: 12pt;">
    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
        {logo_html}
        <div style="text-align: right;">
            <div style="font-size: 22pt; font-weight: bold; color: #2B4C7E; margin-bottom: 4pt;">ESTIMATE</div>
            <div style="font-size: 11pt; color: #333;">Estimate: {extracted_data.get('estimate_number', 'TBD')}</div>
            <div style="font-size: 11pt; color: #333;">Date: {extracted_data.get('date', '')}</div>
            <div style="font-size: 11pt; color: #333;">Addendum: {extracted_data.get('addendum_count', 'No addendums')}</div>
            <div style="font-size: 11pt; color: #333;">Valid for: {extracted_data.get('validity_days', '30')} days</div>
        </div>
    </div>
</div>
```

NOTE: The logo HTML is: {logo_html}
If no logo is available, text fallback "ALL PAINTING LTD." will show.

ADDENDUM FORMATTING RULE:
- If addendum_count is a number (1, 2, 3, etc.), display as "Up to [number]" (e.g., "Up to 3")
- If addendum_count is "No addendums" or empty, display as "No addendums"

SMART CONTACT EXTRACTION RULES (use throughout document):
- Look for ALL phone patterns: (604) 123-4567, 604-123-4567, etc. Include ALL found, separated by " / "
- Look for ALL emails with @ symbol. Include ALL found, separated by " / "
- Look for ALL contact persons. Include ALL found, separated by " / "
- Extract client's company ADDRESS (not just project address)
- Build addresses intelligently: [street], [city], [province] [postal]

2. CLIENT & PROJECT INFO - COPY THIS EXACT TEMPLATE:

```html
<div style="display: flex; gap: 12pt; margin-bottom: 12pt; page-break-inside: avoid !important;">
    <div style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; padding: 12pt; background: white;">
        <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 8pt; border-bottom: 2px solid #2B4C7E; padding-bottom: 4pt;">CLIENT INFORMATION</div>
        <div style="font-size: 11pt; line-height: 1.4;">
            <div style="margin-bottom: 2pt;"><strong>Company:</strong> [company_name - must be BUSINESS name]</div>
            <div style="margin-bottom: 2pt;"><strong>Contact:</strong> [contact_person - may have multiple separated by /]</div>
            <div style="margin-bottom: 2pt;"><strong>Address:</strong> [client address and city_province_postal if available]</div>
            <div style="margin-bottom: 2pt;"><strong>Phone:</strong> [phone - may have multiple separated by /]</div>
            <div style="margin-bottom: 2pt;"><strong>Email:</strong> [email - may have multiple separated by /]</div>
        </div>
    </div>
    <div style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; padding: 12pt; background: white;">
        <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 8pt; border-bottom: 2px solid #2B4C7E; padding-bottom: 4pt;">PROJECT LOCATION</div>
        <div style="font-size: 11pt; line-height: 1.4;">
            <div style="margin-bottom: 2pt;"><strong>Project:</strong> [project name from data]</div>
            <div style="margin-bottom: 2pt;"><strong>Address:</strong> [project address and city_province_postal from data]</div>
        </div>
    </div>
</div>
```

Insert actual data values from extracted_data in place of [bracketed placeholders].

3. EXECUTIVE SUMMARY (NEVER BREAK - class="section no-break", page-break-inside: avoid !important; margin-bottom: 12pt):
   - "EXECUTIVE SUMMARY" header (14pt bold, color #2B4C7E)
   - Table with borders (page-break-inside: avoid !important)
   - Header row: Scope | Description | Amount (11pt bold, background #F5F5F5)
   - Data rows (11pt)
   - Right-align amounts
   - TOTAL (Excluding GST) row at bottom (navy #2B4C7E background, white 12pt bold text): ${subtotal:,.2f}
   - The label must say "TOTAL (Excluding GST)" not "SUBTOTAL"
   - DO NOT include GST row
   - GST is excluded and listed in the EXCLUSIONS section

4. GENERAL TERMS & CONDITIONS (USE page-break-inside: avoid ON THE ENTIRE SECTION):
   
   CRITICAL: Keep the entire terms box together on one page. Do NOT split the box.
   
   SPECIAL FORMATTING RULES FOR GENERAL TERMS:
   - If you see "MPI inspection and MPI warranty not included - Bonding not included" or similar, format it as: <span style="color: #2B4C7E; font-weight: bold;">MPI inspection and MPI warranty not included - Bonding not included</span>
   - If you see "Our price is based on the information in our estimate" (or similar opening statement), format the ENTIRE sentence as: <span style="color: #2B4C7E; font-weight: bold;">Our price is based on the information in our estimate ONLY. If we have missed any details, please contact our office for corrections</span>
   
   EXACT CSS TEMPLATE:
   ```
   <div class="terms-section" style="margin-bottom: 12pt; page-break-inside: avoid;">
       <div style="background: #8B0000; color: white; font-size: 12pt; font-weight: bold; padding: 10pt; border-radius: 8px 8px 0 0;">
           GENERAL TERMS & CONDITIONS
       </div>
       <div style="border: 3px solid #F0E68C; border-top: none; border-radius: 0 0 8px 8px; padding: 10pt; background: #FFF9E6;">
           <ul style="margin: 0; padding-left: 20pt; list-style-type: disc; line-height: 1.35; list-style-position: outside;">
               <li style="font-size: 11pt; margin-bottom: 3pt;">Item 1</li>
               <li style="font-size: 11pt; margin-bottom: 3pt;">Item 2</li>
               <!-- ALL terms in one box -->
           </ul>
       </div>
   </div>
   ```

5. STANDARD INCLUSIONS (USE page-break-inside: avoid ON THE ENTIRE SECTION):
   
   CRITICAL: Keep the entire inclusions box together on one page. Do NOT split the box.
   
   EXACT CSS TEMPLATE:
   ```
   <div class="inclusions-section" style="margin-bottom: 12pt; page-break-inside: avoid;">
       <div style="background: #2B4C7E; color: white; font-size: 12pt; font-weight: bold; padding: 10pt; border-radius: 8px 8px 0 0;">
           STANDARD INCLUSIONS
       </div>
       <div style="border: 3px solid #2B4C7E; border-top: none; border-radius: 0 0 8px 8px; padding: 10pt; background: white;">
           <ul style="margin: 0; padding-left: 20pt; list-style-type: disc; line-height: 1.35; list-style-position: outside;">
               <li style="font-size: 11pt; margin-bottom: 3pt;">Item 1</li>
               <li style="font-size: 11pt; margin-bottom: 3pt;">Item 2</li>
               <!-- ALL inclusions in one box -->
           </ul>
       </div>
   </div>
   ```
   NOTE: Use standard bullet points (list-style-type: disc), NOT checkmarks. Single column layout.

6. DETAILED SCOPE OF WORK (USE page-break-inside: avoid ON EACH SCOPE BOX):
   - Main header "DETAILED SCOPE OF WORK" (14pt bold, color #2B4C7E) at the top
   - Then for EACH item in extracted_data['scope_details'], create a subsection
   
   CRITICAL: Keep each scope box together on one page. Do NOT split boxes mid-content.
   Use page-break-inside: avoid on each scope box.
   
   CRITICAL: Use ALL items from scope_details array. Each scope_detail item has: scope_id, scope_title, and items array.
   
   EXACT CSS TEMPLATE for each scope_detail:
   ```
   <div class="scope-detail-section" style="margin-bottom: 12pt; page-break-inside: avoid;">
       <div style="background: #2B4C7E; color: white; font-size: 12pt; font-weight: bold; padding: 10pt; border-radius: 8px 8px 0 0;">
           {{scope_detail.scope_title}}
       </div>
       <div style="border: 3px solid #2B4C7E; border-top: none; border-radius: 0 0 8px 8px; padding: 10pt; background: white;">
           <ul style="margin: 0; padding-left: 20pt; list-style-type: disc; line-height: 1.35; list-style-position: outside;">
               <li style="font-size: 11pt; margin-bottom: 3pt;">{{item 1}}</li>
               <li style="font-size: 11pt; margin-bottom: 3pt;">{{item 2}}</li>
               <!-- ALL items for this scope in one box -->
           </ul>
       </div>
   </div>
   ```
   
   RULES:
   - Put ALL items for each scope in ONE single box
   - Use page-break-inside: avoid on the outer div to keep each box intact
   - Each scope (EXTERIOR PAINTING, INTERIOR PAINTING, etc.) gets its own complete box

7. EXCLUSIONS (USE page-break-inside: avoid ON THE ENTIRE SECTION):
   
   CRITICAL: Keep the entire exclusions box together on one page. Do NOT split the box.
   Use page-break-inside: avoid to keep the box intact.
   
   SPECIAL FORMATTING RULES FOR EXCLUSIONS:
   - If you see "MPI inspection and MPI warranty not included" or similar, format it as: <span style="color: #2B4C7E; font-weight: bold;">MPI inspection and MPI warranty not included</span>
   
   EXACT CSS TEMPLATE FOR EXCLUSIONS SECTION:
   ```
   <div class="exclusions-section" style="margin-bottom: 12pt; page-break-inside: avoid;">
       <div style="background: #8B0000; color: white; font-size: 12pt; font-weight: bold; padding: 10pt; border-radius: 8px 8px 0 0;">
           EXCLUSIONS
       </div>
       <div style="border: 3px solid #8B0000; border-top: none; border-radius: 0 0 8px 8px; padding: 10pt; background: white;">
           <div style="font-size: 11pt; line-height: 1.35; column-count: 2; column-gap: 20pt;">
               <ul style="margin: 0; padding-left: 20pt; list-style-type: disc; list-style-position: outside;">
                   <li style="margin-bottom: 3pt;">GST (Goods and Services Tax @ 5%)</li>
                   <li style="margin-bottom: 3pt;">Item 2</li>
                   <li style="margin-bottom: 3pt;">Item 3</li>
                   <!-- ALL exclusion items in one box -->
               </ul>
           </div>
       </div>
   </div>
   ```
   
   RULES:
   - Put ALL exclusion items in ONE single box
   - Use column-count: 2 to fit more items
   - GST (Goods and Services Tax @ 5%) MUST ALWAYS be the FIRST item
   - Use page-break-inside: avoid on the outer div to keep box intact

8. WARRANTY & CREDENTIALS (NEVER BREAK - class="section no-break", 2 boxes side by side, page-break-inside: avoid !important; margin-bottom: 12pt):
   
   EXACT CSS TEMPLATE:
   ```
   <div class="warranty-credentials-container" style="display: flex; gap: 12pt; page-break-inside: avoid !important; break-inside: avoid !important; margin-bottom: 12pt;">
       <div class="warranty-box" style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; background: #F8F9FA; padding: 12pt; text-align: center;">
           <div style="font-size: 28pt; margin-bottom: 6pt;">🛡️</div>
           <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 6pt;">WARRANTY</div>
           <div style="font-size: 11pt; font-weight: bold; margin-bottom: 6pt;">2 YEAR WARRANTY</div>
           <div style="font-size: 10pt; line-height: 1.3;">Two Year Limited Warranty on Material and Workmanship. We stand behind our work and will address any warranty issues promptly at no additional cost.</div>
       </div>
       <div class="credentials-box" style="flex: 1; border: 3px solid #2B4C7E; border-radius: 10px; background: #F8F9FA; padding: 12pt;">
           <div style="font-size: 28pt; margin-bottom: 6pt; text-align: center;">🏆</div>
           <div style="font-size: 12pt; font-weight: bold; color: #2B4C7E; margin-bottom: 6pt; text-align: center;">CREDENTIALS & CERTIFICATIONS</div>
           <ul style="margin: 0; padding-left: 25pt !important; list-style-type: disc; line-height: 1.35; list-style-position: outside;">
               <li style="font-size: 10pt; padding-left: 5pt; margin-bottom: 3pt;">Five Million Liability Insurance</li>
               <li style="font-size: 10pt; padding-left: 5pt; margin-bottom: 3pt;">Member of the Better Business Bureau (BBB)</li>
               <li style="font-size: 10pt; padding-left: 5pt; margin-bottom: 3pt;">Current Liability and WCB documents available on request</li>
           </ul>
       </div>
   </div>
   ```
   ```

9. PAYMENT TERMS (NEVER BREAK - class="section no-break", page-break-inside: avoid !important; margin-bottom: 12pt):
   - Header (12pt bold, color #2B4C7E, page-break-after: avoid !important)
   - <ul style="padding-left: 25pt !important; list-style-position: outside;">
   - <li style="font-size: 11pt; padding-left: 5pt; margin-bottom: 3pt;">Payment term</li>

10. FOOTER (Simple line with company info, appears on EVERY page):
    
    EXACT CSS TEMPLATE (this footer will appear automatically on every page):
    ```
    <div id="footer">
        <div style="border-top: 2px solid #2B4C7E; padding-top: 8pt; text-align: center; font-size: 10pt; color: #333;">
            ALL PAINTING LTD | Phone: (604) 525-1403 | www.allpaintingltd.ca
        </div>
    </div>
    ```
    NOTE: Place this div at the very beginning of the body, right after opening <body> tag. The CSS @page rule will make it appear on every page automatically.
    
NOTE: DO NOT include any signature section in the document.

</body>
</html>

CRITICAL FORMATTING RULES:
1. CONSISTENT TYPOGRAPHY - Use exact font sizes specified above everywhere
2. PAGE BREAK CONTROL - USE page-break-inside: avoid ON ALL BOXES:
   - EVERY section box (General Terms, Standard Inclusions, Exclusions, Scope details, Warranty, Payment Terms, Signature) MUST have page-break-inside: avoid on the outer div
   - This keeps each box intact and prevents content from being split awkwardly across pages
   - Do NOT split boxes with "(Continued)" headers - keep each box complete
   - The PDF renderer will automatically place boxes on the next page if they don't fit
3. COMPACT SPACING - margin-bottom: 12pt between sections, padding: 10-12pt, line-height: 1.35
4. ROUNDED CORNERS - Header MUST have border-radius: 10px, Client/Project boxes MUST have border-radius: 10px
5. PROPER CAPITALIZATION - All sentences and bullets start with capital letters
6. ALL CSS INLINE - Include all styles in the HTML
7. PROFESSIONAL APPEARANCE - Clean, organized, easy to read
8. USE EXACT HTML TEMPLATES - Copy the HTML templates provided EXACTLY as shown
9. BULLET POINTS - Use proper <ul> and <li> tags with list-style-type: disc. Use padding-left: 20pt on ul. NO checkmarks or special characters.
10. FOOTER PLACEMENT - Place the footer div (with id="footer") at the VERY BEGINNING of the body tag, right after <body>
11. PAGE NUMBERING - The CSS automatically adds page numbers in the bottom right of each page
12. SMART CONTACT EXTRACTION - Extract ALL contacts, phones, emails (separate multiples with " / "). Include client address. COMPANY NAME must be a business name - check email domain for hints.
13. LINE HEIGHT - Use line-height: 1.35 for body text for better space efficiency
14. GST HANDLING - GST is EXCLUDED. Show "TOTAL (Excluding GST)" in Executive Summary. GST must be FIRST item in Exclusions.
15. BOX INTEGRITY - NEVER split a box across pages. Each box must be complete with header and all content together.

⚠️ FINAL REMINDER:
- Use REAL HTML tags (<div>, <ul>, <li>, <table>) with inline styles
- COPY templates exactly - do not simplify
- border-radius: 10px MUST be on header and info boxes
- NO bullet characters • - use <li> tags inside <ul>

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

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files like logo"""
    return send_from_directory('static', filename)

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
    print("Professional Format Edition - Compact Layout")
    print("="*60)
    if HAS_LOGO:
        print(f"✅ Logo found: {LOGO_PATH}")
    else:
        print(f"⚠️  Logo not found at: {LOGO_PATH}")
        print("   Create a 'static' folder and add 'logo.png' to enable logo")
    print("Server starting on http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
