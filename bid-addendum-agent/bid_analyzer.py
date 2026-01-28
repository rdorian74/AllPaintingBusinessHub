"""
Bid Analyzer - Claude API integration for bid email validation and extraction
All Painting Ltd.

Responsibilities:
1. Validate if email is a legitimate bid/addendum/clarification
2. Extract project details (name, GC, due date, etc.)
3. Check for duplicates against existing bid database
4. Generate forwarding note
"""
import anthropic
import json
import time
import re
from datetime import datetime
import config


def analyze_bid_email(email_data, existing_bids=None):
    """
    Analyze an email to determine if it's a valid bid and extract details
    
    Args:
        email_data: Dictionary with email info (subject, body, from, cc, etc.)
        existing_bids: List of existing bids for duplicate detection
    
    Returns:
        Dictionary with:
        - valid: True/False
        - category: new_bid / addendum / clarification / invalid
        - reason: Why valid/invalid
        - extracted_info: Project details if valid
        - forwarding_note: Short note for Ian
        - matching_bid_id: If this matches an existing bid
        - cost: API cost
        - input_tokens, output_tokens
    """
    start_time = time.time()
    
    # Check for API key
    if not config.ANTHROPIC_API_KEY:
        return {
            "valid": False,
            "category": "error",
            "reason": "ANTHROPIC_API_KEY not configured",
            "cost": 0,
            "input_tokens": 0,
            "output_tokens": 0
        }
    
    # Build the prompt
    prompt = build_analysis_prompt(email_data, existing_bids)
    
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=config.MAX_TOKENS,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Parse response
        response_text = response.content[0].text
        
        # Extract JSON from response
        result = parse_claude_response(response_text)
        
        # Calculate cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (input_tokens * config.COST_PER_1M_INPUT_TOKENS / 1_000_000) + \
               (output_tokens * config.COST_PER_1M_OUTPUT_TOKENS / 1_000_000)
        
        result["cost"] = round(cost, 6)
        result["input_tokens"] = input_tokens
        result["output_tokens"] = output_tokens
        result["processing_time_ms"] = int((time.time() - start_time) * 1000)
        
        return result
    
    except Exception as e:
        return {
            "valid": False,
            "category": "error",
            "reason": f"API error: {str(e)}",
            "cost": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "processing_time_ms": int((time.time() - start_time) * 1000)
        }


def build_analysis_prompt(email_data, existing_bids=None):
    """Build the analysis prompt for Claude"""
    
    subject = email_data.get("subject", "")
    body = email_data.get("body", "")
    body_preview = email_data.get("body_preview", "")
    from_address = email_data.get("from_address", "")
    from_name = email_data.get("from_name", "")
    to_addresses = email_data.get("to_addresses", [])
    cc_addresses = email_data.get("cc_addresses", [])
    received_datetime = email_data.get("received_datetime", "")
    
    # Use body preview if full body is too long or contains too much HTML
    email_content = body_preview if len(body) > 10000 else body
    # Clean HTML tags
    email_content = re.sub(r'<[^>]+>', ' ', email_content)
    email_content = re.sub(r'\s+', ' ', email_content).strip()
    
    prompt = f"""You are an email classifier for All Painting Ltd., a commercial painting contractor.
Analyze this email to determine if it's a legitimate INCOMING bid invitation that should be forwarded to Ian (the estimator).

**TODAY'S DATE: {datetime.now().strftime('%Y-%m-%d')} ({datetime.now().strftime('%A, %B %d, %Y')})**

## EMAIL TO ANALYZE

**From:** {from_name} <{from_address}>
**To:** {', '.join(to_addresses) if to_addresses else 'Unknown'}
**Subject:** {subject}
**CC:** {', '.join(cc_addresses) if cc_addresses else 'None'}
**Email Date:** {received_datetime}

⚠️ **IMPORTANT CHECK**: If the FROM address is info@allpaintingltd.com or any @allpaintingltd.com address, this is an INTERNAL email/forward, NOT an incoming bid. Mark as INVALID.

⚠️ **IMPORTANT CHECK**: If Ian (ianc@allpaintingltd.com or emeraldpainting@gmail.com) is in the TO or CC field, this email was already sent to him - it's likely a manual forward that should not be processed again. Mark as INVALID.

**Body:**
{email_content[:8000]}

## CLASSIFICATION RULES

**VALID emails (forward to Ian - INCOMING bid requests):**
1. **New Bid Invitation**: Invitation to bid on a painting project FROM a general contractor TO us
2. **Addendum**: Update or amendment to an existing bid (usually numbered: Addendum #1, #2, etc.)
3. **Clarification**: Response to questions about a bid, or clarification documents
4. **Bid Documents**: Drawings, specifications, or bid package documents

**⚠️ CRITICAL - CATEGORY SELECTION RULES:**
- If an email is a NEW bid invitation that ALSO mentions addenda have been issued, classify it as "new_bid" (NOT addendum)
- Only classify as "addendum" if the email is SPECIFICALLY about an addendum update (subject contains "Addendum" or "Amendment")
- The PRIMARY purpose of the email determines the category
- If in doubt between new_bid and addendum, choose "new_bid" for initial invitations

**INVALID emails (do NOT forward):**
1. **Outgoing Estimates**: Emails with "Estimate:" or "Quote:" in subject - these are OUR estimates going OUT
2. **Estimate Confirmations**: Replies to our own estimates (e.g., "RE: Estimate: 25C-284...")
3. **Newsletter/Marketing**: Marketing emails, company newsletters, promotional content
4. **Spam**: Unsolicited sales emails, phishing attempts
5. **Internal/Admin**: Account notices, subscription confirmations, automated notifications
6. **Unrelated**: Emails not about construction bids or painting projects
7. **Already Submitted**: Confirmation of bid submission (we submitted, not receiving)
8. **Internal Forwards**: If the email is FROM info@allpaintingltd.com or another All Painting email - it's an internal forward, NOT a new bid

**IMPORTANT: If the email subject contains "Estimate:" followed by a reference number (like "Estimate: 25C-284"), this is an OUTGOING estimate from All Painting, NOT an incoming bid request. Mark as INVALID.**

## GC CONTACT EMAIL - IMPORTANT

**IGNORE these tracking/system email addresses and extract the REAL contact email from the email body:**
- Anything ending in @shared1.ccsend.com (Constant Contact)
- Anything ending in @smartbidnet.com (SmartBidNet)
- Anything ending in @buildingconnected.com (BuildingConnected - look for real GC email in body)
- Anything containing "notifications@" or "noreply@"

If the From address is one of these tracking emails, look in the email body for the actual GC contact email address.

## ⚠️ CRITICAL: BID DUE DATE EXTRACTION ⚠️

**THIS IS THE MOST IMPORTANT FIELD - YOU MUST FIND AND EXTRACT THE DATE**

**READ THE ENTIRE EMAIL BODY CAREFULLY - The deadline is almost always mentioned somewhere.**

**Search for ALL of these trigger phrases (case-insensitive):**
1. **Tender/Bid closing phrases:**
   - "Tender closing" / "Tender closes"
   - "Bid closing" / "Bid closes" / "Bids close"
   - "Closing date" / "Close date"
   - "Tender due" / "Tenders due"
   
2. **Due/Deadline phrases:**
   - "Due by" / "Due date" / "Due on" / "Due:"
   - "Deadline" / "Deadline:"
   - "Bids due" / "Bid due" / "Pricing due"
   - "Submit by" / "Submission deadline" / "Submission date"
   
3. **Price/Quote request phrases:**
   - "I will need your price before"
   - "Please submit your price by"
   - "Need your quote by"
   - "Pricing required by"
   - "Please provide pricing by"
   - "Quote deadline"
   
4. **Response/Return phrases:**
   - "Please respond by"
   - "Response required by"
   - "Return by"
   - "RSVP by"

**Date formats to recognize and convert:**
- "February 8th, 2026" → "2026-02-08"
- "February 8, 2026" → "2026-02-08"
- "Feb 8, 2026" → "2026-02-08"
- "Feb 8th, 2026" → "2026-02-08"
- "8th February 2026" → "2026-02-08"
- "02/08/2026" or "2/8/2026" → "2026-02-08"
- "08-Feb-2026" → "2026-02-08"
- "2026-02-08" → "2026-02-08"
- "February 8" (no year) → assume current/next year → "2026-02-08"

**Day + Date combinations:**
- "Tuesday, February 8th" → "2026-02-08"
- "on February 8th" → "2026-02-08"
- "before February 8th" → "2026-02-08"

**Relative dates (calculate from today):**
- "next Tuesday" → calculate actual date
- "this Friday" → calculate actual date
- "in 2 weeks" → calculate actual date
- "by end of month" → last day of current month
- "end of January" → last day of January

**EXAMPLES FROM REAL EMAILS:**
- "Tender closing: I will need your price before 12 noon on February 8th, 2026" → "2026-02-08"
- "Bids are due by 2:00 PM on Tuesday, January 28th" → "2026-01-28"
- "Please submit your bid no later than January 28, 2026" → "2026-01-28"
- "Deadline: Jan 28/26" → "2026-01-28"
- "Pricing due: January 28" → "2026-01-28"
- "Tender closes January 30, 2026 at 2pm" → "2026-01-30"
- "We need your price by Friday" → calculate the date

**IMPORTANT RULES:**
1. ALWAYS convert to YYYY-MM-DD format
2. If year is not specified, assume 2026 (or current year if date has passed)
3. If no explicit date but email mentions "ASAP" or "urgent", use 7 days from email date
4. If this is an addendum, look for UPDATED/NEW deadline dates
5. **DO NOT return null for bid_due_date if ANY date reference exists in the email**

**BID DUE TIME:**
- Look for times near the deadline: "12 noon", "2:00 PM", "10:00am", "end of day", "COB"
- "noon" or "12 noon" = "12:00 PM"
- "COB" or "end of day" or "close of business" = "5:00 PM"
- Include timezone if mentioned (e.g., "2:00 PM PST", "10:00 AM Pacific")
- Default to "2:00 PM PST" if date found but no time specified

**GC CONTACT INFO - EXTRACT FROM EMAIL SIGNATURE:**
- **Contact Name**: Look carefully in the signature block, "From:", "Contact:", "Estimator:", "Project Manager:", "Sent by:"
- **Phone**: Look for phone/cell/mobile/office numbers in signature - format: xxx-xxx-xxxx or (xxx) xxx-xxxx
- **Email**: Find the REAL email, not tracking emails

**GC COMPANY:**
- Check email signature, letterhead, company name in body
- Look for "Inc.", "Ltd.", "LLC", "Construction", "Contractors", "Builders"

**PROJECT ADDRESS:**
- Look for street addresses, city names, locations
- Include full address: street, city, province/state if available

## WHAT TO EXTRACT (if valid)

- **Project Name**: The name of the project (e.g., "Vancouver Library Renovation")
- **Bid Reference Number**: Official bid/tender number if provided
- **GC Company**: General contractor company name
- **GC Contact Name**: Person's full name from email signature
- **GC Phone**: Phone number from email signature
- **GC Contact Email**: The REAL email address, NOT tracking emails
- **Bid Due Date**: Deadline date (format: YYYY-MM-DD) - THIS IS CRITICAL
- **Bid Due Time**: Deadline time (default "2:00 PM PST" if date found but no time)
- **Project Address**: Location of the project
- **Project Type**: Commercial / Residential / Government / Institutional / Other
- **Scope of Work**: Brief description of painting scope if mentioned
- **Addendum Number**: If this is an addendum, what number (1, 2, 3, etc.)

"""

    # Add existing bids for duplicate detection
    if existing_bids:
        prompt += """
## EXISTING BIDS IN DATABASE (for duplicate detection)

**Check if this email is about the SAME PROJECT as any existing bid.**
**Match by: project address, GC company + similar project name, or same GC contact email.**

"""
        for bid in existing_bids[:30]:  # Increased from 20 to 30
            prompt += f"""- ID: {bid.get('id')} | Project: {bid.get('project_name', 'Unknown')} | GC: {bid.get('gc_company', 'Unknown')} | Address: {bid.get('project_address', 'N/A')} | Due: {bid.get('bid_due_date', 'Unknown')} | Addendum: {bid.get('current_addendum', 0)}
"""
        
        prompt += """
If this email is an addendum or update for an existing bid, provide the matching bid ID.
"""

    prompt += """
## RESPONSE FORMAT

Respond with ONLY this JSON structure (no other text):

```json
{
    "valid": true or false,
    "category": "new_bid" | "addendum" | "clarification" | "invalid",
    "reason": "Brief explanation of why this is valid/invalid",
    "confidence": "high" | "medium" | "low",
    "extracted_info": {
        "project_name": "string or null",
        "bid_reference_number": "string or null",
        "gc_company": "string or null - CHECK EMAIL SIGNATURE AND LETTERHEAD",
        "gc_contact_name": "string or null - LOOK IN EMAIL SIGNATURE BLOCK",
        "gc_phone": "string or null - LOOK IN EMAIL SIGNATURE FOR PHONE NUMBERS",
        "gc_contact_email": "REAL email address - NOT tracking emails like @ccsend.com or @buildingconnected.com",
        "bid_due_date": "YYYY-MM-DD format ONLY or null - CONVERT ALL DATES",
        "bid_due_time": "string with timezone or null (e.g., '2:00 PM PST')",
        "project_address": "full street address or null",
        "project_type": "Commercial/Residential/Government/Institutional or null",
        "scope_of_work": "string or null",
        "addendum_number": number or null
    },
    "matching_bid_id": number or null,
    "forwarding_note": "2-3 sentence summary for Ian explaining what this email is about"
}
```

CRITICAL REMINDERS:
1. If subject contains "Estimate:" with a reference number -> INVALID (it's our outgoing estimate)
2. Extract REAL GC email, not tracking emails (@ccsend.com, @smartbidnet.com, @buildingconnected.com)
3. Check existing bids for duplicates - same project address or same GC + similar name = match existing bid
4. Convert all dates to YYYY-MM-DD format
5. Be strict about classification - if in doubt, err on the side of marking as invalid
"""
    
    return prompt


def parse_claude_response(response_text):
    """Parse Claude's JSON response"""
    
    # Try to extract JSON from the response
    try:
        # Look for JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError("No JSON found in response")
        
        result = json.loads(json_str)
        
        # Ensure required fields
        if "valid" not in result:
            result["valid"] = False
        if "category" not in result:
            result["category"] = "unknown"
        if "reason" not in result:
            result["reason"] = "No reason provided"
        if "extracted_info" not in result:
            result["extracted_info"] = {}
        if "forwarding_note" not in result:
            result["forwarding_note"] = ""
        
        return result
    
    except Exception as e:
        return {
            "valid": False,
            "category": "error",
            "reason": f"Failed to parse response: {str(e)}",
            "extracted_info": {},
            "forwarding_note": ""
        }


def generate_forwarding_note(analysis_result, email_subject):
    """Generate HTML note for the forwarded email"""
    
    category = analysis_result.get("category", "unknown")
    info = analysis_result.get("extracted_info", {})
    claude_note = analysis_result.get("forwarding_note", "")
    
    # Category emoji and label
    category_labels = {
        "new_bid": ("📋", "NEW BID DETECTED"),
        "addendum": ("📝", "ADDENDUM DETECTED"),
        "clarification": ("💬", "CLARIFICATION")
    }
    emoji, label = category_labels.get(category, ("📧", "BID EMAIL"))
    
    # Build the note with friendly greeting
    html = f"""
<div style="font-family: Arial, sans-serif; padding: 15px; background-color: #f0f7ff; border-left: 4px solid #0066cc; margin-bottom: 20px;">
    <p style="margin: 0 0 15px 0; font-size: 14px;">Hi Ian,<br><br>This just arrived. Please take a look at the summary below.</p>
    
    <h3 style="margin: 0 0 10px 0; color: #0066cc;">{emoji} {label}</h3>
    
    <p style="margin: 5px 0;"><strong>Summary:</strong> {claude_note}</p>
"""
    
    # Add extracted details if available
    details = []
    if info.get("project_name"):
        details.append(f"<strong>Project:</strong> {info['project_name']}")
    if info.get("gc_company"):
        details.append(f"<strong>GC:</strong> {info['gc_company']}")
    if info.get("bid_due_date"):
        due_str = info['bid_due_date']
        if info.get("bid_due_time"):
            due_str += f" @ {info['bid_due_time']}"
        details.append(f"<strong>Due:</strong> {due_str}")
    if info.get("addendum_number"):
        details.append(f"<strong>Addendum #:</strong> {info['addendum_number']}")
    
    if details:
        html += f"""
    <div style="margin-top: 10px; padding: 10px; background-color: white; border-radius: 4px;">
        {'<br>'.join(details)}
    </div>
"""
    
    html += f"""
    <p style="margin: 10px 0 0 0; font-size: 12px; color: #666;">
        Auto-forwarded by Bid/Addendum Agent | {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </p>
</div>
"""
    
    return html


# Test the analyzer if run directly
if __name__ == "__main__":
    print("Testing Bid Analyzer...")
    
    # Test email data
    test_email = {
        "subject": "Invitation to Bid - Vancouver Public Library Renovation",
        "body": """Dear Contractors,

ABC Construction Ltd. is pleased to invite you to bid on the Vancouver Public Library Renovation project.

Project: Vancouver Public Library - Main Branch Renovation
Location: 350 West Georgia Street, Vancouver, BC
Bid Due: February 15, 2025 at 2:00 PM PST

Scope of work includes interior and exterior painting of the renovated areas.

Please confirm your interest by replying to this email.

Best regards,
John Smith
Senior Estimator
ABC Construction Ltd.
604-555-1234
""",
        "from_address": "john.smith@abcconstruction.com",
        "from_name": "John Smith",
        "cc_addresses": []
    }
    
    # Test without API (will fail gracefully)
    result = analyze_bid_email(test_email)
    print(f"\nAnalysis result:")
    print(json.dumps(result, indent=2))
