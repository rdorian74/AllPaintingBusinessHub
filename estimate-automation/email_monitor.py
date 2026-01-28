"""
Email Monitor - Watches for new estimate emails from Ian
IMPROVED VERSION - Better filtering to avoid false positives
"""
import re
from datetime import datetime
from outlook_client import OutlookClient
import config


class EmailMonitor:
    """Monitors inbox for estimate emails from Ian"""
    
    def __init__(self):
        self.outlook = OutlookClient()
        self.processed_email_ids = set()
    
    def extract_estimate_code(self, text):
        """
        Extract estimate code from text (e.g., 25C-318, 25C318, 25C-325-A)
        Only matches valid All Painting estimate codes (2 digits + C or R + 3 digits)
        
        Args:
            text: Text to search (subject, body, attachment names)
        
        Returns:
            Extracted code or None
        """
        # Pattern: 2 digits (year) + C or R (commercial/residential) + optional dash + 3 digits + optional version letter
        # Examples: 25C-318, 25C318, 25C-325-A, 25C325B, 26R-001
        # Must be 24, 25, 26, 27, etc. for year
        pattern = r'(2[4-9][CR]-?\d{3}(?:-?[A-Za-z])?)'
        
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            # Return the first match, normalized (uppercase)
            return matches[0].upper()
        
        return None
    
    def normalize_estimate_code(self, code):
        """
        Normalize estimate code to standard format for searching
        Returns both with-dash and without-dash versions
        
        Args:
            code: Estimate code (e.g., 25C-318 or 25C318)
        
        Returns:
            Tuple of (with_dash, without_dash) versions
        """
        # Remove any dashes first
        clean = code.replace("-", "").upper()
        
        # Extract parts: 2 digits, 1 letter (C or R), 3 digits, optional letter
        match = re.match(r'(\d{2})([CR])(\d{3})([A-Za-z])?', clean, re.IGNORECASE)
        
        if match:
            prefix = match.group(1)  # 25
            letter = match.group(2).upper()  # C or R
            number = match.group(3)  # 318
            version = match.group(4) or ""  # A or empty
            
            with_dash = f"{prefix}{letter}-{number}"
            without_dash = f"{prefix}{letter}{number}"
            
            if version:
                with_dash += f"-{version.upper()}"
                without_dash += version.upper()
            
            return (with_dash, without_dash)
        
        return (code.upper(), code.replace("-", "").upper())
    
    def is_valid_estimate_code(self, code):
        """
        Validate that the code is a proper All Painting estimate code
        
        Args:
            code: Potential estimate code
        
        Returns:
            True if valid estimate code format
        """
        if not code:
            return False
        
        # Must match pattern: 2 digits (24-29) + C or R + 3 digits
        pattern = r'^2[4-9][CR]-?\d{3}(-?[A-Za-z])?$'
        return bool(re.match(pattern, code, re.IGNORECASE))
    
    def has_estimate_keywords(self, text):
        """
        Check if text contains estimate-related keywords
        
        Args:
            text: Text to check
        
        Returns:
            True if contains keywords
        """
        text_lower = text.lower()
        for keyword in config.ESTIMATE_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
        return False
    
    def is_estimate_email(self, email):
        """
        Check if an email is a valid estimate notification from Ian
        
        IMPROVED LOGIC:
        1. Must be from Ian
        2. Must contain a valid estimate code (25C-XXX, 26R-XXX, etc.)
        3. Should have keywords OR attachments with estimate code
        
        Args:
            email: Email object from Microsoft Graph
        
        Returns:
            True if this is a valid estimate email
        """
        # Check sender
        sender = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        
        if sender not in [e.lower() for e in config.IAN_EMAILS]:
            return False
        
        subject = email.get("subject", "")
        body = email.get("body", {}).get("content", "")
        text_to_check = f"{subject} {body}"
        
        # First, try to find a valid estimate code
        code = self.extract_estimate_code(text_to_check)
        
        # If no code in subject/body, check attachments
        if not code and email.get("hasAttachments"):
            try:
                attachments = self.outlook.get_email_attachments(email["id"])
                for att in attachments:
                    att_name = att.get("name", "")
                    code = self.extract_estimate_code(att_name)
                    if code:
                        break
            except Exception as e:
                print(f"   Warning: Could not get attachments: {e}")
        
        # MUST have a valid estimate code
        if not code or not self.is_valid_estimate_code(code):
            return False
        
        # If we have a code, check for keywords (optional but preferred)
        has_keywords = self.has_estimate_keywords(text_to_check)
        
        # Also accept if attachments contain the code (like "25C-325 Takeoff.xlsx")
        has_estimate_attachment = False
        if email.get("hasAttachments"):
            try:
                attachments = self.outlook.get_email_attachments(email["id"])
                for att in attachments:
                    att_name = att.get("name", "")
                    if self.extract_estimate_code(att_name):
                        has_estimate_attachment = True
                        break
            except:
                pass
        
        # Accept if has keywords OR has attachment with estimate code
        return has_keywords or has_estimate_attachment
    
    def get_estimate_info_from_email(self, email):
        """
        Extract estimate information from an email
        
        Args:
            email: Email object from Microsoft Graph
        
        Returns:
            Dictionary with estimate code and other info, or None
        """
        subject = email.get("subject", "")
        body = email.get("body", {}).get("content", "")
        
        # Try to extract code from subject first
        code = self.extract_estimate_code(subject)
        
        # If not in subject, try body
        if not code:
            code = self.extract_estimate_code(body)
        
        # If still not found, check attachments
        if not code and email.get("hasAttachments"):
            try:
                attachments = self.outlook.get_email_attachments(email["id"])
                for att in attachments:
                    att_name = att.get("name", "")
                    code = self.extract_estimate_code(att_name)
                    if code:
                        break
            except Exception as e:
                print(f"Warning: Could not get attachments: {e}")
        
        # Validate the code
        if code and self.is_valid_estimate_code(code):
            return {
                "code": code,
                "code_variants": self.normalize_estimate_code(code),
                "email_id": email["id"],
                "subject": subject,
                "received_at": email.get("receivedDateTime"),
                "sender": email.get("from", {}).get("emailAddress", {}).get("address")
            }
        
        return None
    
    def check_for_new_estimates(self, minutes_back=None):
        """
        Check for new estimate emails
        
        Args:
            minutes_back: How many minutes back to search (default from config)
        
        Returns:
            List of estimate info dictionaries for new estimates
        """
        if minutes_back is None:
            minutes_back = config.CHECK_INTERVAL_SECONDS // 60 + 2  # Add buffer
        
        new_estimates = []
        
        try:
            # Get recent emails from Ian
            emails = self.outlook.get_recent_emails(
                minutes_back=minutes_back,
                from_addresses=config.IAN_EMAILS
            )
            
            print(f"   Found {len(emails)} emails from Ian in last {minutes_back} minutes")
            
            for email in emails:
                email_id = email["id"]
                subject = email.get("subject", "")[:50]
                
                # Skip if already processed
                if email_id in self.processed_email_ids:
                    continue
                
                # Check if it's a valid estimate email
                if self.is_estimate_email(email):
                    estimate_info = self.get_estimate_info_from_email(email)
                    
                    if estimate_info:
                        new_estimates.append(estimate_info)
                        self.processed_email_ids.add(email_id)
                        print(f"   ✅ Valid estimate email: {estimate_info['code']} - {subject}")
                    else:
                        print(f"   ⚠️ Could not extract code from: {subject}")
                else:
                    # Mark as processed so we don't check it again
                    self.processed_email_ids.add(email_id)
                    print(f"   ⏭️ Skipping (not an estimate): {subject}")
        
        except Exception as e:
            print(f"❌ Error checking emails: {e}")
        
        return new_estimates
    
    def mark_as_processed(self, email_id):
        """Mark an email as processed"""
        self.processed_email_ids.add(email_id)
    
    def reset_processed(self):
        """Reset the processed emails set (useful for testing)"""
        self.processed_email_ids.clear()


# Test the monitor if run directly
if __name__ == "__main__":
    print("Testing Email Monitor...")
    
    monitor = EmailMonitor()
    
    # Test code extraction and validation
    test_cases = [
        ("25C-325 Takeoff sheet.xlsx", True),
        ("Rod see attached breakout for 25C318", True),
        ("Project 25C-325-A Interior Painting", True),
        ("26R-001 Residential estimate", True),
        ("Bid Invite: Langara Nursing Dept Reno Project", False),
        ("FW: Painting Quote Requested- YVR Airport", False),
        ("No code here", False),
        ("00D373F something", False),
        ("23C560 old estimate", True),
    ]
    
    print("\nTesting code extraction and validation:")
    for test, expected_valid in test_cases:
        code = monitor.extract_estimate_code(test)
        is_valid = monitor.is_valid_estimate_code(code) if code else False
        status = "✅" if is_valid == expected_valid else "❌"
        print(f"  {status} '{test[:40]}...' -> code={code}, valid={is_valid}")
    
    # Test connection and email checking
    print("\nTesting email check (last 60 minutes)...")
    estimates = monitor.check_for_new_estimates(minutes_back=60)
    print(f"\nFound {len(estimates)} valid estimate emails")
    for est in estimates:
        print(f"  - {est['code']}: {est['subject'][:50]}")
