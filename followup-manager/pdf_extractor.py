"""
Follow Up Manager - PDF Extractor
Regex-based extraction with AI fallback when results are poor
"""
import re
import base64
import tempfile
import os
import json
import logging
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from config import ESTIMATE_CODE_PATTERN, ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

class PDFExtractor:
    def __init__(self):
        if pdfplumber is None:
            raise ImportError("pdfplumber required")
        self._ai_client = None
    
    def _get_ai_client(self):
        """Lazy load AI client"""
        if self._ai_client is None:
            try:
                import anthropic
                self._ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            except:
                pass
        return self._ai_client
    
    def extract_from_base64(self, base64_content):
        """Extract data from base64 PDF"""
        try:
            pdf_bytes = base64.b64decode(base64_content)
        except:
            return None
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        try:
            text = self._extract_text(tmp_path)
            if text and len(text) > 50:
                # Try regex first
                result = self._parse_text(text)
                
                # Check if extraction is poor (missing key fields)
                if self._is_poor_extraction(result):
                    logger.info("  Regex extraction poor, trying AI...")
                    ai_result = self._ai_extract(text)
                    if ai_result:
                        # Merge AI results with regex (AI fills gaps)
                        result = self._merge_results(result, ai_result)
                
                return result
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
        
        return None
    
    def _is_poor_extraction(self, result):
        """Check if extraction is missing important fields or has garbage data"""
        if not result:
            return True
        
        def is_garbage(val):
            """Check if a value is garbage data"""
            if not val or not isinstance(val, str):
                return True
            val_lower = val.lower().strip()
            # Common garbage patterns
            if val_lower.startswith('page ') and ' of ' in val_lower:
                return True
            if val_lower.startswith('re:') or val_lower.startswith('fw:'):
                return True
            if val_lower.startswith('email:') or val_lower.startswith('phone:'):
                return True
            if 'project:' in val_lower and len(val) > 60:
                return True
            if 'address:' in val_lower and len(val) > 80:
                return True
            if val_lower.startswith('http') or val_lower.startswith('www.'):
                return True
            return False
        
        gc_company = result.get("gc_company", "")
        contact_name = result.get("contact_name", "")
        project_name = result.get("project_name", "")
        total_amount = result.get("total_amount")
        
        # Check for garbage in key fields
        has_good_company = gc_company and not is_garbage(gc_company)
        has_good_contact = contact_name and not is_garbage(contact_name)
        has_good_project = project_name and not is_garbage(project_name)
        has_amount = total_amount is not None and total_amount > 0
        
        # Poor if: no company AND no contact, OR no project, OR no amount
        if not has_good_company and not has_good_contact:
            return True
        if not has_good_project:
            return True
        if not has_amount:
            return True
        
        return False
    
    def _merge_results(self, regex_result, ai_result):
        """Merge AI results into regex results (AI fills gaps)"""
        if not regex_result:
            return ai_result
        if not ai_result:
            return regex_result
        
        merged = regex_result.copy()
        for key, value in ai_result.items():
            # Only use AI value if regex is missing or bad
            regex_val = merged.get(key)
            if not regex_val or (isinstance(regex_val, str) and regex_val.startswith("Page ")):
                merged[key] = value
        
        return merged
    
    def _ai_extract(self, text):
        """Use AI to extract data from PDF text"""
        client = self._get_ai_client()
        if not client:
            return None
        
        try:
            prompt = f"""You are extracting data from a painting estimate PDF. Extract ONLY the specific fields requested.

CRITICAL RULES:
1. Each field must contain ONLY that specific piece of information - no mixing
2. gc_company = ONLY the company name (e.g., "Titan Construction Ltd" not "Titan Construction Ltd Project: Something")
3. contact_name = ONLY the person's name (e.g., "John Smith" not "John Smith November 10, 2025")
4. DO NOT include dates, addresses, project names, or other text in the wrong fields
5. DO NOT concatenate multiple pieces of information
6. If you can't find clean data for a field, use null

PDF TEXT:
{text[:5000]}

Extract these fields:

gc_company: The general contractor or client company name ONLY. 
- Look for company suffixes like Ltd, Inc, Corp, Construction, Group
- DO NOT include "Project:", addresses, or descriptions
- Example: "Titan Construction Limited" ✓
- Bad example: "Titan Construction Limited Project: OTC Building" ✗

contact_name: The contact person's full name ONLY.
- Look for "Attn:", "Contact:", or names near phone/email
- DO NOT include dates, titles, or "Address:"
- Example: "Richard Coleman" ✓
- Bad example: "Richard Coleman November 10, 2025" ✗

contact_email: Email address only

contact_phone: Phone number only

project_name: The project name/description.
- Look for "Project:", "Re:", or description after company name
- Example: "Interior Painting - RBC Oakridge"

project_address: The project street address only.
- Example: "949 West 41st Avenue, Vancouver, BC"

total_amount: The total dollar amount as a number.
- Look for "TOTAL", "Grand Total", or sum of scopes
- Return just the number (e.g., 25000.00)

Return ONLY valid JSON:
{{"gc_company": "...", "contact_name": "...", "contact_email": "...", "contact_phone": "...", "project_name": "...", "project_address": "...", "total_amount": ...}}"""

            # Use Opus for better accuracy
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Parse JSON - handle nested braces
            start = result_text.find('{')
            end = result_text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = result_text[start:end]
                data = json.loads(json_str)
                
                # Clean the data - remove any fields that look wrong
                cleaned = {}
                for k, v in data.items():
                    if v is None:
                        continue
                    if isinstance(v, str):
                        v = v.strip()
                        # Skip bad extractions
                        if v.lower().startswith('page ') and ' of ' in v.lower():
                            continue
                        if k == 'gc_company' and ('Project:' in v or 'Address:' in v or len(v) > 80):
                            # Try to extract just the company name
                            if 'Project:' in v:
                                v = v.split('Project:')[0].strip()
                            if len(v) > 80:
                                continue
                        if k == 'contact_name':
                            # Remove dates from contact names
                            import re as re2
                            v = re2.sub(r'\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}', '', v).strip()
                            v = re2.sub(r'\s+Address:.*$', '', v).strip()
                            if len(v) > 50:
                                continue
                        if v:
                            cleaned[k] = v
                    else:
                        cleaned[k] = v
                
                return cleaned
            
        except Exception as e:
            logger.warning(f"AI extraction failed: {e}")
        
        return None
    
    def _extract_text(self, file_path):
        """Extract text from PDF"""
        text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        except Exception as e:
            logger.error(f"PDF read error: {e}")
        return text
    
    def _parse_text(self, text):
        """Parse PDF text with regex - handles both old and new formats"""
        result = {}
        
        # Estimate code (handles 25C-174-A format too)
        for pattern in [
            r'OUR\s+ESTIMATE\s*#?\s*(2[4-9][CR][-\s]?\d{3}(?:[-\s]?[A-Z])?)',
            r'Estimate[:\s]+(2[4-9][CR][-\s]?\d{3})',
            ESTIMATE_CODE_PATTERN
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                code = m.group(1).upper().replace(" ", "-")
                # Normalize: 25C174-A -> 25C-174-A
                if re.match(r'^\d{2}[CR]\d{3}', code):
                    code = code[:3] + "-" + code[3:]
                result["estimate_code"] = code
                break
        
        # Date - multiple formats
        for pattern in [
            r'(\w+\s+\d{1,2},?\s+\d{4})',  # July 15, 2025
            r'Date[:\s]+(\w+\s+\d{1,2},?\s+\d{4})',
        ]:
            m = re.search(pattern, text)
            if m:
                parsed = self._parse_date(m.group(1))
                if parsed:
                    result["estimate_date"] = parsed
                    break
        
        # Contact name - OLD format: "Attn: Name"
        m = re.search(r'Attn[:\s]+([^\n]+)', text, re.IGNORECASE)
        if m:
            result["contact_name"] = m.group(1).strip()
        
        # Contact name - NEW format: "Contact: Name"  
        if not result.get("contact_name"):
            m = re.search(r'Contact[:\s]+([^\n]+)', text)
            if m:
                result["contact_name"] = m.group(1).strip()
        
        # Company name - OLD format: Line after Attn (before address)
        # Look for company name pattern (ends with Ltd, Inc, Corp, Services, etc.)
        m = re.search(r'Attn:[^\n]+\n([A-Z][^\n]+(?:Ltd|Inc|Corp|Services|Construction|Group|Contracting)[^\n]*)', text, re.IGNORECASE)
        if m:
            result["gc_company"] = m.group(1).strip()
        
        # Company - NEW format: "Company: Name"
        if not result.get("gc_company"):
            m = re.search(r'Company[:\s]+([^\n]+)', text)
            if m:
                result["gc_company"] = m.group(1).strip()
        
        # Email (not ours)
        for email in re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text):
            if 'allpainting' not in email.lower():
                result["contact_email"] = email
                break
        
        # Phone - multiple patterns
        for pattern in [
            r'Telephone[:\s]*([\d\-\(\)\s\.]{10,})',
            r'Cell[:\s]*([\d\-\(\)\s\.]{10,})',
            r'Ph\.?\s*([\d\-\(\)\s\.]{10,})',
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                result["contact_phone"] = m.group(1).strip()
                break
        
        # Project name - OLD format: "Project Reference:" followed by name on next line
        m = re.search(r'Project\s+Reference[:\s]*\n\s*([^\n]+)', text, re.IGNORECASE)
        if m:
            proj = m.group(1).strip()
            if proj and not proj.startswith('#') and len(proj) > 2:
                result["project_name"] = proj
        
        # Project name - NEW format: "Project: Name"
        if not result.get("project_name"):
            m = re.search(r'Project[:\s]+([^\n]+?)(?:\n|Address)', text)
            if m:
                result["project_name"] = m.group(1).strip()
        
        # Address - OLD format: Line after project name (city pattern)
        m = re.search(r'Project\s+Reference[:\s]*\n[^\n]+\n\s*(\d+[^\n]+)', text, re.IGNORECASE)
        if m:
            addr = m.group(1).strip()
            if 'allpainting' not in addr.lower():
                result["project_address"] = addr
        
        # Address - NEW format
        if not result.get("project_address"):
            m = re.search(r'(?:Project\s+)?Address[:\s]+([^\n]+)', text)
            if m:
                addr = m.group(1).strip()
                if 'allpainting' not in addr.lower():
                    result["project_address"] = addr
        
        # Total amount - try single TOTAL first
        total_found = False
        for pattern in [
            r'TOTAL\s*\(?[Ee]xcluding\s*GST\)?\s*\$?([\d,]+\.?\d*)',
            r'Total[:\s]*\$?\s*([\d,]+\.?\d*)'
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    result["total_amount"] = float(m.group(1).replace(",", ""))
                    total_found = True
                    break
                except:
                    pass
        
        # If no single total, sum Project Scope amounts (OLD format)
        if not total_found:
            scope_amounts = re.findall(r'Project\s+Scope\s*#?\d+\)[^\$]*\$\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
            if scope_amounts:
                try:
                    total = sum(float(a.replace(",", "")) for a in scope_amounts)
                    if total > 0:
                        result["total_amount"] = total
                except:
                    pass
        
        return result if result else None
    
    def _parse_date(self, date_str):
        """Parse date string"""
        if not date_str:
            return None
        date_str = date_str.replace(",", "").strip()
        for fmt in ["%B %d %Y", "%m/%d/%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except:
                pass
        return None


# Singleton
_extractor = None
def get_pdf_extractor():
    global _extractor
    if _extractor is None:
        _extractor = PDFExtractor()
    return _extractor
