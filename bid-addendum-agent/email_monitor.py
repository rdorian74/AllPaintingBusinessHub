"""
Email Monitor - Watches for bid/addendum emails
Bid/Addendum Agent - All Painting Ltd.

Responsibilities:
1. Poll inbox for new emails
2. Keyword scan (free, before Claude API)
3. Filter out Ian's emails (loop protection)
4. Pass to Claude for validation
"""
import re
from datetime import datetime
from outlook_client import OutlookClient
from bid_analyzer import analyze_bid_email, generate_forwarding_note
from database import Database
import config


class BidEmailMonitor:
    """Monitors inbox for bid/addendum emails"""
    
    def __init__(self):
        self.outlook = OutlookClient()
        self.db = Database()
        self.processed_email_ids = set()
        
        # Load already processed emails from database
        self._load_processed_emails()
    
    def _load_processed_emails(self):
        """Load processed email IDs from database"""
        logs = self.db.get_processing_log(limit=1000)
        for log in logs:
            if log.get("message_id"):
                self.processed_email_ids.add(log["message_id"])
    
    def keyword_scan(self, text):
        """
        Quick keyword scan (free, before Claude API)
        
        Args:
            text: Text to scan (subject + body)
        
        Returns:
            List of matched keywords, or empty list if none
        """
        text_lower = text.lower()
        # Normalize text - remove extra whitespace, handle common variations
        text_lower = re.sub(r'\s+', ' ', text_lower)
        
        matched = []
        for keyword in config.BID_KEYWORDS:
            # Use word boundary matching for short keywords to avoid false positives
            if len(keyword) <= 3:
                # Short keywords need word boundaries
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    matched.append(keyword)
            else:
                # Longer keywords can use simple contains
                if keyword.lower() in text_lower:
                    matched.append(keyword)
        
        return matched
    
    def is_from_ian(self, email):
        """Check if email is from Ian (loop protection)"""
        sender = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        return sender in [e.lower() for e in config.IAN_EMAILS]
    
    def is_internal_or_forwarded(self, email):
        """
        Check if email is internal, forwarded by us, or sent TO Ian
        This prevents processing our own outgoing emails and manual forwards.
        
        Returns:
            (bool, str): (should_skip, reason)
        """
        sender = email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        subject = email.get("subject", "").lower()
        
        # Get TO recipients
        to_recipients = email.get("toRecipients", [])
        to_addresses = [r.get("emailAddress", {}).get("address", "").lower() for r in to_recipients]
        
        # Get CC recipients
        cc_recipients = email.get("ccRecipients", [])
        cc_addresses = [r.get("emailAddress", {}).get("address", "").lower() for r in cc_recipients]
        
        all_recipients = to_addresses + cc_addresses
        
        # Check 1: If sender is Ian - skip
        if sender in [e.lower() for e in config.IAN_EMAILS]:
            return True, "Sent by Ian (loop protection)"
        
        # Check 2: If sender is our internal email (we forwarded it) - skip
        internal_emails = [e.lower() for e in getattr(config, 'INTERNAL_EMAILS', [])]
        if sender in internal_emails:
            return True, "Sent from internal email (loop protection)"
        
        # Check 3: If email was explicitly sent TO Ian (we forwarded it manually) - skip
        ian_emails_lower = [e.lower() for e in config.IAN_EMAILS]
        for recipient in all_recipients:
            if recipient in ian_emails_lower:
                return True, "Already sent to Ian (manual forward detected)"
        
        # Check 4: Subject indicates it's a forward by us (subject starts with FW: and we are in TO/CC)
        if subject.startswith("fw:") or subject.startswith("fwd:"):
            for recipient in all_recipients:
                if recipient in internal_emails:
                    return True, "Forward of email already involving our addresses"
        
        # Check 5: Subject contains our bid detection markers (already processed)
        if "new bid detected" in subject.lower() or "addendum detected" in subject.lower():
            return True, "Already processed - contains detection marker in subject"
        
        return False, None
    
    def extract_email_domain(self, email_address):
        """Extract domain from email address"""
        if "@" in email_address:
            return email_address.split("@")[1].lower()
        return None
    
    def process_email(self, email):
        """
        Process a single email through the full pipeline
        
        Args:
            email: Email object from Microsoft Graph
        
        Returns:
            Dictionary with processing result
        """
        message_id = email["id"]
        internet_message_id = email.get("internetMessageId", "")  # More stable ID for dedup
        subject = email.get("subject", "")
        body = email.get("body", {}).get("content", "")
        body_preview = email.get("bodyPreview", "")
        from_address = email.get("from", {}).get("emailAddress", {}).get("address", "")
        from_name = email.get("from", {}).get("emailAddress", {}).get("name", "")
        received_at = email.get("receivedDateTime", "")
        
        # Extract CC addresses
        cc_recipients = email.get("ccRecipients", [])
        cc_addresses = [r.get("emailAddress", {}).get("address", "") for r in cc_recipients]
        
        print(f"\n   📧 Processing: {subject[:60]}...")
        print(f"      From: {from_name} <{from_address}>")
        
        # Step 1: Check if already processed
        if self.db.is_email_processed(message_id):
            print(f"      ⏭️ Already processed (message_id), skipping")
            return {"status": "already_processed", "message_id": message_id}
        
        # Also check by internet_message_id (more stable across forwards)
        if internet_message_id and self.db.is_email_processed_by_internet_id(internet_message_id):
            print(f"      ⏭️ Already processed (internet_message_id), skipping")
            return {"status": "already_processed", "message_id": message_id}
        
        # Step 2: Comprehensive loop protection - check for internal/forwarded emails
        should_skip, skip_reason = self.is_internal_or_forwarded(email)
        if should_skip:
            print(f"      ⏭️ {skip_reason}")
            self.db.add_processing_log(
                message_id=message_id,
                internet_message_id=internet_message_id,
                subject=subject,
                from_address=from_address,
                status="skipped",
                skip_reason=skip_reason,
                from_name=from_name,
                received_at=received_at
            )
            return {"status": "skipped", "reason": "internal_or_forwarded", "message_id": message_id}
        
        # Legacy check - keep for backward compatibility
        if self.is_from_ian(email):
            print(f"      ⏭️ From Ian, skipping (loop protection)")
            self.db.add_processing_log(
                message_id=message_id,
                internet_message_id=internet_message_id,
                subject=subject,
                from_address=from_address,
                status="skipped",
                skip_reason="Loop protection - email from Ian",
                from_name=from_name,
                received_at=received_at
            )
            return {"status": "skipped", "reason": "from_ian", "message_id": message_id}
        
        # Step 3: Keyword scan (free)
        text_to_scan = f"{subject} {body_preview}"
        matched_keywords = self.keyword_scan(text_to_scan)
        
        if not matched_keywords:
            print(f"      ⏭️ No bid keywords found, skipping")
            self.db.add_processing_log(
                message_id=message_id,
                subject=subject,
                from_address=from_address,
                status="skipped",
                skip_reason="No bid keywords matched",
                from_name=from_name,
                received_at=received_at,
                body_preview=body_preview[:500]
            )
            return {"status": "skipped", "reason": "no_keywords", "message_id": message_id}
        
        print(f"      ✅ Keywords matched: {', '.join(matched_keywords[:5])}")
        
        # Step 3.5: Check if we've already processed a similar email recently
        # This prevents the same bid being detected as both new_bid and addendum
        recent_similar = self.db.get_processing_by_subject_and_sender(subject, from_address, hours_back=2)
        if recent_similar:
            forwarded_or_drafted = [r for r in recent_similar if r.get('status') in ['forwarded', 'draft_created']]
            if forwarded_or_drafted:
                print(f"      ⏭️ Similar email from same sender already processed recently")
                self.db.add_processing_log(
                    message_id=message_id,
                    internet_message_id=internet_message_id,
                    subject=subject,
                    from_address=from_address,
                    status="skipped",
                    skip_reason=f"Duplicate - similar email already forwarded/drafted (log ID: {forwarded_or_drafted[0]['id']})",
                    from_name=from_name,
                    received_at=received_at,
                    body_preview=body_preview[:500],
                    matched_keywords=matched_keywords
                )
                return {"status": "skipped", "reason": "duplicate_recent", "message_id": message_id}
        
        # Step 4: Claude API validation
        print(f"      🤖 Calling Claude for validation...")
        
        # Get existing bids for duplicate detection
        existing_bids = self.db.get_open_bids(limit=50)
        
        # Get TO recipients for loop detection
        to_recipients = email.get("toRecipients", [])
        to_addresses = [r.get("emailAddress", {}).get("address", "") for r in to_recipients]
        
        email_data = {
            "subject": subject,
            "body": body,
            "body_preview": body_preview,
            "from_address": from_address,
            "from_name": from_name,
            "to_addresses": to_addresses,
            "cc_addresses": cc_addresses,
            "received_datetime": received_at
        }
        
        analysis = analyze_bid_email(email_data, existing_bids)
        
        print(f"      📊 Claude result: valid={analysis.get('valid')}, category={analysis.get('category')}")
        print(f"      💰 Cost: ${analysis.get('cost', 0):.4f}")
        
        # Step 5: Handle result based on validity
        if not analysis.get("valid"):
            print(f"      ❌ Invalid: {analysis.get('reason', 'Unknown')}")
            self.db.add_processing_log(
                message_id=message_id,
                subject=subject,
                from_address=from_address,
                status="skipped",
                category=analysis.get("category", "invalid"),
                skip_reason=analysis.get("reason", "Claude marked invalid"),
                from_name=from_name,
                received_at=received_at,
                body_preview=body_preview[:500],
                matched_keywords=matched_keywords,
                claude_summary=analysis.get("forwarding_note", ""),
                cost_usd=analysis.get("cost", 0),
                input_tokens=analysis.get("input_tokens", 0),
                output_tokens=analysis.get("output_tokens", 0)
            )
            return {
                "status": "skipped", 
                "reason": "claude_invalid", 
                "message_id": message_id,
                "analysis": analysis
            }
        
        # Valid bid email - process it
        print(f"      ✅ Valid bid email!")
        
        extracted = analysis.get("extracted_info", {})
        category = analysis.get("category", "new_bid")
        matching_bid_id = analysis.get("matching_bid_id")
        
        # Step 6: Update or create bid tracker entry
        bid_id = None
        
        if matching_bid_id:
            # This is an update to an existing bid
            print(f"      📝 Matches existing bid ID: {matching_bid_id}")
            bid_id = matching_bid_id
            
            if category == "addendum":
                self.db.increment_addendum(bid_id, datetime.now().isoformat())
                print(f"      📝 Incremented addendum count")
            
            # Add this email to the bid's source emails
            self.db.add_email_to_bid(bid_id, message_id, subject)
            
            # Update any new information
            updates = {}
            if extracted.get("bid_due_date"):
                updates["bid_due_date"] = extracted["bid_due_date"]
            if extracted.get("bid_due_time"):
                updates["bid_due_time"] = extracted["bid_due_time"]
            if updates:
                self.db.update_bid(bid_id, **updates)
        else:
            # New bid - create entry
            print(f"      📋 Creating new bid entry")
            bid_id = self.db.add_bid(
                project_name=extracted.get("project_name"),
                gc_company=extracted.get("gc_company"),
                gc_contact_email=from_address,
                gc_contact_name=extracted.get("gc_contact_name") or from_name,
                gc_phone=extracted.get("gc_phone"),
                bid_due_date=extracted.get("bid_due_date"),
                bid_due_time=extracted.get("bid_due_time"),
                bid_reference_number=extracted.get("bid_reference_number"),
                project_address=extracted.get("project_address"),
                project_type=extracted.get("project_type"),
                scope_of_work=extracted.get("scope_of_work"),
                original_bid_email_date=received_at,
                source_email_ids=[message_id],
                all_email_subjects=[subject]
            )
            print(f"      📋 Created bid ID: {bid_id}")
        
        # Step 7: Update GC contacts database
        email_domain = self.extract_email_domain(from_address)
        if email_domain:
            self.db.add_or_update_gc(
                email_domain=email_domain,
                company_name=extracted.get("gc_company"),
                contact_name=extracted.get("gc_contact_name") or from_name,
                contact_email=from_address,
                phone=extracted.get("gc_phone")
            )
        
        # Step 8: Create draft or forward based on mode
        mode = self.db.get_setting("mode", config.OPERATION_MODE)
        forwarding_note = generate_forwarding_note(analysis, subject)
        
        action_taken = None
        draft_id = None
        
        if mode == "draft":
            # Create forward draft in the designated folder (preserves attachments)
            print(f"      📝 Creating forward draft (mode=draft)...")
            try:
                folder_id = self.outlook.get_or_create_folder(config.DRAFTS_FOLDER_NAME)
                draft = self.outlook.create_forward_draft(
                    original_message_id=message_id,
                    to_email=config.FORWARD_TO_EMAIL,
                    comment_html=forwarding_note,
                    folder_id=folder_id
                )
                draft_id = draft.get("id")
                action_taken = "draft_created"
                print(f"      ✅ Forward draft created in '{config.DRAFTS_FOLDER_NAME}'")
            except Exception as e:
                print(f"      ❌ Error creating forward draft: {e}")
                import traceback
                traceback.print_exc()
                action_taken = "draft_error"
        
        elif mode == "active":
            # Forward the email directly
            print(f"      📤 Forwarding email (mode=active)...")
            try:
                self.outlook.forward_email(
                    message_id=message_id,
                    to_email=config.FORWARD_TO_EMAIL,
                    comment_html=forwarding_note
                )
                action_taken = "forwarded"
                print(f"      ✅ Email forwarded to {config.FORWARD_TO_EMAIL}")
            except Exception as e:
                print(f"      ❌ Error forwarding: {e}")
                action_taken = "forward_error"
        
        # Step 9: Log the processing
        status = "draft_created" if action_taken == "draft_created" else "forwarded" if action_taken == "forwarded" else "error"
        
        self.db.add_processing_log(
            message_id=message_id,
            subject=subject,
            from_address=from_address,
            status=status,
            category=category,
            from_name=from_name,
            cc_addresses=cc_addresses,
            received_at=received_at,
            body_preview=body_preview[:500],
            matched_keywords=matched_keywords,
            claude_summary=analysis.get("forwarding_note", ""),
            claude_extracted_data=extracted,
            bid_tracker_id=bid_id,
            action_taken=action_taken,
            draft_id=draft_id,
            cost_usd=analysis.get("cost", 0),
            input_tokens=analysis.get("input_tokens", 0),
            output_tokens=analysis.get("output_tokens", 0)
        )
        
        self.processed_email_ids.add(message_id)
        
        return {
            "status": status,
            "message_id": message_id,
            "bid_id": bid_id,
            "category": category,
            "action_taken": action_taken,
            "analysis": analysis
        }
    
    def check_for_new_bids(self, minutes_back=None):
        """
        Check for new bid emails
        
        Args:
            minutes_back: How many minutes back to search
        
        Returns:
            List of processing results
        """
        if minutes_back is None:
            minutes_back = config.CHECK_INTERVAL_SECONDS // 60 + 2  # Add buffer
        
        results = []
        
        try:
            # Get recent emails (excluding Ian's)
            emails = self.outlook.get_recent_emails(
                minutes_back=minutes_back,
                exclude_addresses=config.IAN_EMAILS
            )
            
            print(f"   Found {len(emails)} emails (excluding Ian) in last {minutes_back} minutes")
            
            for email in emails:
                # Skip if already processed (quick check)
                if email["id"] in self.processed_email_ids:
                    continue
                
                # Process the email
                result = self.process_email(email)
                results.append(result)
        
        except Exception as e:
            print(f"❌ Error checking emails: {e}")
            import traceback
            traceback.print_exc()
        
        return results


# Test the monitor if run directly
if __name__ == "__main__":
    print("Testing Bid Email Monitor...")
    
    monitor = BidEmailMonitor()
    
    # Test keyword scan
    test_texts = [
        "Invitation to Bid - Vancouver Library Renovation",
        "Addendum #2 - Project XYZ",
        "RFP for Painting Services",
        "Your Amazon order has shipped",
        "Newsletter: Construction Industry Update",
        "Bid Due Date Extended to Feb 15",
        "Pre-qualification Required",
    ]
    
    print("\nKeyword scan tests:")
    for text in test_texts:
        matches = monitor.keyword_scan(text)
        status = "✅" if matches else "❌"
        print(f"  {status} '{text[:50]}' -> {matches if matches else 'no match'}")
    
    # Test connection
    print("\nTesting email check (last 30 minutes)...")
    results = monitor.check_for_new_bids(minutes_back=30)
    
    print(f"\nProcessed {len(results)} emails:")
    for r in results:
        print(f"  - Status: {r.get('status')}, Category: {r.get('category', 'N/A')}")
