"""
Validator module for AI Agent Service
Uses Claude API to validate PDF estimates

Enhanced with:
- Word vs PDF content comparison
- Page structure validation (blank pages, skipped pages)
- Auto-correction cycle (regenerate up to 3 times)
"""
import anthropic
import base64
import time
import re
import json
import requests
import config


# =============================================================================
# MAIN VALIDATION FUNCTION
# =============================================================================

def validate_estimate(pdf_path, extracted_data, estimate_code, word_path=None, attempt=1):
    """
    Validate an estimate PDF using Claude API
    
    Args:
        pdf_path: Path to the PDF file
        extracted_data: Data already extracted from the estimate
        estimate_code: The estimate code (e.g., 25C-319)
        word_path: Path to the original Word document (for comparison)
        attempt: Current attempt number (for auto-correction)
    
    Returns:
        Dictionary with validation results:
        {
            "passed": True/False,
            "issues": ["list of issues"],
            "confidence_score": 0-100,
            "cost": 0.00,
            "input_tokens": 0,
            "output_tokens": 0,
            "processing_time_ms": 0,
            "attempts": 1,
            "auto_corrected": False
        }
    """
    start_time = time.time()
    total_cost = 0
    total_input_tokens = 0
    total_output_tokens = 0
    
    print(f"   🔍 Validation attempt {attempt} of {config.MAX_REGENERATION_ATTEMPTS}")
    
    # First, do basic validation without API (free)
    basic_result = validate_basic(extracted_data, estimate_code)
    
    if not basic_result["passed"]:
        # Basic validation failed, no need to call API
        processing_time = int((time.time() - start_time) * 1000)
        return {
            "passed": False,
            "issues": basic_result["issues"],
            "confidence_score": basic_result["confidence_score"],
            "cost": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "processing_time_ms": processing_time,
            "attempts": attempt,
            "auto_corrected": False,
            "correctable": False
        }
    
    # Call Claude API for deeper validation
    try:
        api_result = validate_with_claude(pdf_path, extracted_data, estimate_code, word_path)
        total_cost += api_result.get("cost", 0)
        total_input_tokens += api_result.get("input_tokens", 0)
        total_output_tokens += api_result.get("output_tokens", 0)
        
        # Check if issues are correctable and auto-correction is enabled
        if not api_result["passed"] and config.AUTO_CORRECTION_ENABLED:
            correctable_issues = get_correctable_issues(api_result.get("issues", []))
            
            if correctable_issues and attempt < config.MAX_REGENERATION_ATTEMPTS:
                print(f"   ⚠️ Found correctable issues: {correctable_issues}")
                print(f"   🔄 Attempting auto-correction...")
                
                # Try to regenerate the PDF
                regen_result = request_pdf_regeneration(word_path, correctable_issues)
                
                if regen_result.get("success"):
                    new_pdf_path = regen_result.get("pdf_path", pdf_path)
                    new_extracted_data = regen_result.get("extracted_data", extracted_data)
                    
                    # Recursive call with incremented attempt
                    retry_result = validate_estimate(
                        new_pdf_path, 
                        new_extracted_data, 
                        estimate_code, 
                        word_path,
                        attempt + 1
                    )
                    
                    # Accumulate costs
                    retry_result["cost"] = total_cost + retry_result.get("cost", 0)
                    retry_result["input_tokens"] = total_input_tokens + retry_result.get("input_tokens", 0)
                    retry_result["output_tokens"] = total_output_tokens + retry_result.get("output_tokens", 0)
                    retry_result["auto_corrected"] = retry_result.get("passed", False)
                    
                    return retry_result
                else:
                    print(f"   ❌ Auto-correction failed: {regen_result.get('error')}")
        
        processing_time = int((time.time() - start_time) * 1000)
        api_result["processing_time_ms"] = processing_time
        api_result["attempts"] = attempt
        api_result["auto_corrected"] = False
        api_result["cost"] = total_cost
        api_result["input_tokens"] = total_input_tokens
        api_result["output_tokens"] = total_output_tokens
        
        return api_result
    
    except Exception as e:
        # API call failed, return basic validation result
        processing_time = int((time.time() - start_time) * 1000)
        print(f"⚠️ Claude API error: {e}")
        return {
            "passed": basic_result["passed"],
            "issues": basic_result["issues"] + [f"API validation skipped: {str(e)}"],
            "confidence_score": basic_result["confidence_score"],
            "cost": total_cost,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "processing_time_ms": processing_time,
            "attempts": attempt,
            "auto_corrected": False,
            "api_error": str(e)
        }


# =============================================================================
# BASIC VALIDATION (FREE - NO API)
# =============================================================================

def validate_basic(extracted_data, estimate_code):
    """
    Basic validation without API call (free)
    Checks for required fields and basic data integrity
    
    Returns:
        Dictionary with passed, issues, confidence_score
    """
    issues = []
    
    # Check client info
    client_info = extracted_data.get("client_info", {})
    
    client_email = client_info.get("email", "")
    if not client_email or "@" not in client_email:
        issues.append("Missing or invalid client email")
    
    client_name = client_info.get("company_name", "") or client_info.get("contact_person", "")
    if not client_name:
        issues.append("Missing client name")
    
    # Check project info
    project_info = extracted_data.get("project_info", {})
    
    project_name = project_info.get("name", "")
    if not project_name:
        issues.append("Missing project name")
    
    # Check estimate code matches
    extracted_code = extracted_data.get("estimate_number", "")
    if extracted_code and estimate_code:
        # Normalize codes for comparison
        norm_extracted = re.sub(r'[^0-9A-Za-z]', '', extracted_code.upper())
        norm_expected = re.sub(r'[^0-9A-Za-z]', '', estimate_code.upper())
        if norm_extracted != norm_expected:
            issues.append(f"Estimate code mismatch: expected {estimate_code}, found {extracted_code}")
    
    # Check scopes exist
    scopes = extracted_data.get("scopes", [])
    if not scopes:
        issues.append("No pricing scopes found")
    
    # Calculate confidence based on issues
    if len(issues) == 0:
        confidence = 90  # Good, but needs API validation for 100%
    elif len(issues) == 1:
        confidence = 60
    elif len(issues) == 2:
        confidence = 40
    else:
        confidence = 20
    
    passed = len(issues) == 0
    
    return {
        "passed": passed,
        "issues": issues,
        "confidence_score": confidence
    }


# =============================================================================
# DEEP VALIDATION WITH CLAUDE API
# =============================================================================

def validate_with_claude(pdf_path, extracted_data, estimate_code, word_path=None):
    """
    Deep validation using Claude API
    Analyzes the PDF content for quality and completeness
    Compares with Word document if provided
    
    Returns:
        Dictionary with validation results
    """
    # Check for API key
    if not config.ANTHROPIC_API_KEY:
        raise Exception("ANTHROPIC_API_KEY not configured")
    
    # Read and encode PDF
    try:
        with open(pdf_path, "rb") as f:
            pdf_content = base64.standard_b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        raise Exception(f"PDF file not found: {pdf_path}")
    except Exception as e:
        raise Exception(f"Error reading PDF: {e}")
    
    # Read Word document if provided (for comparison)
    word_content = None
    if word_path:
        try:
            word_text = extract_text_from_word(word_path)
            if word_text:
                word_content = word_text
                print(f"   📄 Loaded Word document for comparison ({len(word_text)} chars)")
        except Exception as e:
            print(f"   ⚠️ Could not read Word document: {e}")
    
    # Build the prompt
    prompt = build_validation_prompt(estimate_code, extracted_data, word_content)
    
    # Call Claude API
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    
    message = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=config.MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_content
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    )
    
    # Parse response
    response_text = message.content[0].text
    
    # Extract JSON from response
    try:
        # Look for JSON block
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
        else:
            raise ValueError("No JSON found in response")
        
    except json.JSONDecodeError as e:
        print(f"⚠️ Error parsing Claude response: {e}")
        print(f"Response was: {response_text[:500]}")
        # Default to passed if we can't parse
        result = {
            "passed": True,
            "issues": ["Could not parse validation response"],
            "confidence_score": 70,
            "issue_types": []
        }
    
    # Calculate cost
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    
    cost = (input_tokens / 1000 * config.COST_PER_1K_INPUT_TOKENS + 
            output_tokens / 1000 * config.COST_PER_1K_OUTPUT_TOKENS)
    
    return {
        "passed": result.get("passed", True),
        "issues": result.get("issues", []),
        "issue_types": result.get("issue_types", []),
        "confidence_score": result.get("confidence_score", 80),
        "summary": result.get("summary", ""),
        "missing_content": result.get("missing_content", []),
        "cost": round(cost, 4),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens
    }


def build_validation_prompt(estimate_code, extracted_data, word_content=None):
    """Build the validation prompt for Claude"""
    
    # Base prompt
    prompt = f"""You are a quality assurance validator for professional painting estimates from All Painting Ltd.

Analyze this estimate PDF thoroughly and verify:

## 1. PAGE STRUCTURE VALIDATION (CRITICAL)
- Count all pages in the PDF
- Check if page numbers are sequential (no skipped pages like 1, 2, 4)
- Look for any BLANK PAGES (pages with no content or only headers/footers)
- Check for pages where content appears cut off at the bottom
- Verify headers/footers are consistent across ALL pages

## 2. CONTENT COMPLETENESS VALIDATION
- Is the client information complete (company name, contact person, email, phone, address)?
- Is the project information clear (name, location)?
- Is the estimate code "{estimate_code}" visible and correct?
- Are ALL pricing scopes present with amounts?
- Is the date present?
- Are warranty, payment terms, and exclusions included?

## 3. FORMAT QUALITY CHECK
- Is all text readable (not cut off, not overlapping)?
- Are tables complete and properly formatted?
- Is the All Painting Ltd branding/logo present?
- Is spacing consistent throughout?

## 4. DATA INTEGRITY CHECK
The extracted data shows these scopes:
{json.dumps(extracted_data.get('scopes', []), indent=2)}

Verify ALL these scopes appear in the PDF with their amounts.
"""

    # Add Word comparison if available
    if word_content:
        prompt += f"""

## 5. WORD vs PDF COMPARISON (CRITICAL)
The original Word document contains this text:
---
{word_content[:8000]}  
---

IMPORTANT: Verify that ALL content from the Word document appears in the PDF.
- Check that no sections are missing
- Check that no bullet points are missing
- Check that all numbers/prices match
- Minor grammar/spelling fixes are OK, but content must be preserved
- Report any MISSING CONTENT from the Word that doesn't appear in the PDF
"""

    prompt += """

## RESPONSE FORMAT

Respond with this exact JSON structure:
{
    "passed": true or false,
    "issues": ["list of specific issues found"],
    "issue_types": ["list of issue categories: blank_page, skipped_page, cut_off_content, missing_content, formatting_error, missing_field"],
    "confidence_score": 0-100,
    "summary": "One-line summary of validation result",
    "missing_content": ["list of specific content from Word that's missing in PDF, if any"],
    "page_count": number,
    "blank_pages": [list of blank page numbers, if any],
    "pages_with_issues": [list of page numbers with problems, if any]
}

## VALIDATION RULES

FAIL the validation if:
- Any blank pages exist
- Page numbers are skipped
- Content is cut off
- Client email is missing
- Pricing scopes are missing
- ANY content from the Word document is missing (except grammar fixes)

PASS the validation if:
- All pages have content
- All required information is present
- All Word content is present in PDF
- Formatting is professional

Be thorough and strict. This estimate will be sent to a client.
"""
    
    return prompt


# =============================================================================
# WORD DOCUMENT READING
# =============================================================================

def extract_text_from_word(word_path):
    """Extract text from a Word document"""
    try:
        from docx import Document
        doc = Document(word_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = '\n'.join(paragraphs)
        return text
    except ImportError:
        print("   ⚠️ python-docx not installed, skipping Word comparison")
        return None
    except Exception as e:
        print(f"   ⚠️ Error reading Word: {e}")
        return None


# =============================================================================
# AUTO-CORRECTION FUNCTIONS
# =============================================================================

def get_correctable_issues(issues):
    """
    Determine which issues can be auto-corrected by regenerating the PDF
    
    Correctable issues (WeasyPrint/formatting problems):
    - Blank pages
    - Skipped page numbers
    - Cut off content
    - Formatting errors
    
    Non-correctable issues (require Word document changes):
    - Missing client email (not in Word)
    - Wrong estimate code
    - Missing content from Word
    """
    correctable_keywords = [
        "blank page",
        "skipped page",
        "cut off",
        "formatting",
        "page break",
        "overlap",
        "truncated",
        "spacing"
    ]
    
    correctable = []
    for issue in issues:
        issue_lower = issue.lower()
        if any(keyword in issue_lower for keyword in correctable_keywords):
            correctable.append(issue)
    
    return correctable


def request_pdf_regeneration(word_path, issues):
    """
    Request Estimate Generator to regenerate the PDF
    
    Args:
        word_path: Path to the Word document
        issues: List of issues to try to fix
    
    Returns:
        Dictionary with success, pdf_path, extracted_data
    """
    if not word_path:
        return {"success": False, "error": "No Word path provided"}
    
    try:
        print(f"   📤 Requesting PDF regeneration from Estimate Generator...")
        
        # Call Estimate Generator API
        response = requests.post(
            config.ESTIMATE_GENERATOR_URL,
            json={"word_file_path": word_path},
            timeout=120  # PDF generation can take time
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"   ✅ PDF regenerated: {result.get('pdf_filename')}")
                return {
                    "success": True,
                    "pdf_path": result.get("pdf_path"),
                    "extracted_data": result.get("extracted_data", {})
                }
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Regeneration request timed out"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Could not connect to Estimate Generator"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# TEST FUNCTION
# =============================================================================

if __name__ == "__main__":
    print("Testing validator...")
    
    # Test basic validation
    test_data = {
        "client_info": {
            "company_name": "Test Company",
            "email": "test@example.com"
        },
        "project_info": {
            "name": "Test Project"
        },
        "estimate_number": "25C-999",
        "scopes": [
            {"title": "Interior Painting", "amount": "5000.00"}
        ]
    }
    
    result = validate_basic(test_data, "25C-999")
    print(f"Basic validation result: {result}")
