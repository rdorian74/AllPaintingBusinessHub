"""
Follow Up Manager - Email Scanner
Scans Outlook, processes estimates, generates drafts
"""
import re
import logging
from datetime import datetime, timedelta
from html import unescape
from collections import defaultdict

from config import ESTIMATE_CODE_PATTERN, SUBJECT_PATTERN, MAX_EMAIL_BODY_CHARS
from database import (
    create_estimate, get_estimate_by_code, update_estimate,
    create_communication, email_exists, get_communications_for_estimate,
    get_setting, set_setting, get_estimate, get_followups_for_estimate,
    get_all_estimates, get_connection
)
from outlook_client import get_outlook_client
from pdf_extractor import get_pdf_extractor
from ai_analyzer import get_ai_analyzer

logger = logging.getLogger(__name__)

class EmailScanner:
    def __init__(self):
        self.outlook = get_outlook_client()
        self.pdf_extractor = get_pdf_extractor()
        self.ai_analyzer = get_ai_analyzer()
        self._followup_engine = None
    
    def _get_followup_engine(self):
        if self._followup_engine is None:
            from followup_engine import get_followup_engine
            self._followup_engine = get_followup_engine()
        return self._followup_engine
    
    def scan(self, days_back=7, backfill=False):
        """Main scan - groups by estimate, processes once each"""
        results = {
            "new_estimates": 0, "updated_estimates": 0, "new_communications": 0,
            "drafts_generated": 0, "errors": [], "scanned_sent": 0, "scanned_inbox": 0
        }
        
        start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        try:
            # === STEP 1: Fetch sent emails ===
            logger.info("Fetching sent emails...")
            sent_emails = self.outlook.get_sent_emails(start_date)
            results["scanned_sent"] = len(sent_emails)
            logger.info(f"Found {len(sent_emails)} sent emails")
            
            # === STEP 2: Group by estimate code ===
            estimate_emails = defaultdict(list)
            for email in sent_emails:
                subject = email.get("subject", "")
                if self._is_estimate_email(subject):
                    code = self._extract_estimate_code(subject)
                    if code:
                        estimate_emails[code].append(email)
            
            logger.info(f"Found {len(estimate_emails)} unique estimates")
            
            # === STEP 3: Process each estimate ===
            for code, emails in estimate_emails.items():
                try:
                    logger.info(f"Processing: {code} ({len(emails)} emails)")
                    estimate_id = self._process_estimate(code, emails, results)
                    
                    if estimate_id:
                        # Store communications
                        for email in emails:
                            if not email_exists(email.get("id")):
                                self._store_communication(email, estimate_id, "sent", results)
                except Exception as e:
                    logger.error(f"Error {code}: {e}")
                    results["errors"].append(f"{code}: {e}")
            
            # === STEP 4: Process inbox ===
            logger.info("Fetching inbox emails...")
            inbox_emails = self.outlook.get_inbox_emails(start_date)
            results["scanned_inbox"] = len(inbox_emails)
            logger.info(f"Found {len(inbox_emails)} inbox emails")
            
            # Group inbox emails by estimate
            inbox_by_estimate = defaultdict(list)
            
            for email in inbox_emails:
                email_id = email.get("id")
                if email_exists(email_id):
                    continue
                
                estimate = None
                
                # Find by code in subject
                code = self._extract_estimate_code(email.get("subject", ""))
                if code:
                    estimate = get_estimate_by_code(code)
                
                # Find by conversation ID
                if not estimate:
                    conv_id = email.get("conversationId")
                    if conv_id:
                        with get_connection() as conn:
                            row = conn.execute(
                                "SELECT estimate_id FROM communications WHERE conversation_id=? LIMIT 1",
                                (conv_id,)
                            ).fetchone()
                            if row:
                                estimate = get_estimate(row["estimate_id"])
                
                if estimate:
                    inbox_by_estimate[estimate["id"]].append((email, estimate))
            
            # Process each estimate's replies ONCE
            for estimate_id, email_list in inbox_by_estimate.items():
                estimate = email_list[0][1]  # Get estimate from first tuple
                logger.info(f"Processing {len(email_list)} replies for {estimate['estimate_code']}")
                
                # Store all communications first
                for email, _ in email_list:
                    self._store_communication(email, estimate_id, "received", results)
                
                # Get latest reply for date
                latest_email = max(email_list, key=lambda x: x[0].get("receivedDateTime", ""))[0]
                
                # Analyze conversation ONCE with full history
                self._update_after_reply(estimate, latest_email)
            
            # === STEP 5: Generate due drafts ===
            logger.info("Checking for due follow-ups...")
            self._generate_due_drafts(results)
            
            # === STEP 6: Save state ===
            set_setting("last_scan_date", datetime.now().isoformat())
            if backfill:
                set_setting("backfill_completed", "true")
            
            logger.info(f"Scan complete: {results['new_estimates']} new, {results['drafts_generated']} drafts")
            
        except Exception as e:
            logger.error(f"Scan error: {e}")
            results["errors"].append(str(e))
        
        return results
    
    def _process_estimate(self, code, emails, results):
        """Process a single estimate - handles revisions and never overwrites newer data with older"""
        # Sort newest first
        emails.sort(key=lambda e: e.get("sentDateTime", ""), reverse=True)
        latest = emails[0]
        oldest = emails[-1]
        
        # Check if any email in this batch is a revision and get full display code
        is_revision = False
        display_code = code  # Default to group key
        for email in emails:
            parsed = self._parse_estimate_code_full(email.get("subject", ""))
            if parsed:
                if parsed.get("is_revision"):
                    is_revision = True
                # Get the full display code from the latest email
                if parsed.get("display_code"):
                    display_code = parsed.get("display_code")
        
        existing = get_estimate_by_code(code)
        
        data = {"estimate_code": code}  # Group key for lookups
        
        # Extract from PDF (first one with attachment)
        for email in emails:
            if email.get("hasAttachments"):
                try:
                    pdf = self._extract_pdf(email.get("id"))
                    if pdf:
                        data.update(pdf)
                        data["estimate_code"] = code  # Keep group key
                        logger.info(f"  PDF: {pdf.get('gc_company', '')[:30]}")
                        break
                except Exception as e:
                    logger.warning(f"  PDF error: {e}")
        
        # Parse subject for fallback
        subject_data = self._parse_subject(latest.get("subject", ""))
        for k, v in subject_data.items():
            if not data.get(k):
                data[k] = v
        
        # Recipient
        to = latest.get("toRecipients", [])
        if to:
            data["contact_email"] = to[0].get("emailAddress", {}).get("address")
        
        # Dates from this batch
        batch_oldest_date = oldest.get("sentDateTime", "")[:10]
        batch_latest_date = latest.get("sentDateTime", "")[:10]
        batch_latest_id = latest.get("id")
        
        if existing:
            # PROTECT: Only update dates if this batch has newer data
            existing_last_contact = existing.get("last_contact_date") or "1900-01-01"
            existing_estimate_date = existing.get("estimate_date") or "9999-12-31"
            
            # Update last_contact_date only if batch has newer
            if batch_latest_date >= existing_last_contact:
                data["last_contact_date"] = batch_latest_date
                data["original_message_id"] = batch_latest_id
                data["display_code"] = display_code  # Update display code to latest
                
                # Recalculate next follow-up based on newer date
                first_days = int(get_setting("first_followup_days", 17))
                next_date = datetime.strptime(batch_latest_date, "%Y-%m-%d") + timedelta(days=first_days)
                data["next_followup_date"] = next_date.strftime("%Y-%m-%d")
                
                # If this is a revision, increment revision_number
                if is_revision:
                    current_rev = existing.get("revision_number") or 0
                    data["revision_number"] = current_rev + 1
                    logger.info(f"  Revision detected: Rev {data['revision_number']}")
            
            # Update estimate_date only if batch has older (original send)
            if batch_oldest_date < existing_estimate_date:
                data["estimate_date"] = batch_oldest_date
            
            update_estimate(existing["id"], data)
            results["updated_estimates"] += 1
            logger.info(f"  Updated ID {existing['id']}")
            return existing["id"]
        else:
            # New estimate - use all dates
            data["estimate_date"] = batch_oldest_date
            data["last_contact_date"] = batch_latest_date
            data["original_message_id"] = batch_latest_id
            data["display_code"] = display_code
            data["revision_number"] = 1 if is_revision else 0
            
            # Calculate next follow-up
            first_days = int(get_setting("first_followup_days", 17))
            if batch_latest_date:
                next_date = datetime.strptime(batch_latest_date, "%Y-%m-%d") + timedelta(days=first_days)
                data["next_followup_date"] = next_date.strftime("%Y-%m-%d")
            
            est_id = create_estimate(data)
            results["new_estimates"] += 1
            logger.info(f"  Created ID {est_id}")
            return est_id
    
    def _process_inbox_email(self, email, results):
        """Process inbox email for replies"""
        email_id = email.get("id")
        if email_exists(email_id):
            return
        
        estimate = None
        
        # Find by code in subject
        code = self._extract_estimate_code(email.get("subject", ""))
        if code:
            estimate = get_estimate_by_code(code)
            if estimate:
                logger.info(f"Reply matched: {code}")
        
        # Find by conversation ID
        if not estimate:
            conv_id = email.get("conversationId")
            if conv_id:
                with get_connection() as conn:
                    row = conn.execute(
                        "SELECT estimate_id FROM communications WHERE conversation_id=? LIMIT 1",
                        (conv_id,)
                    ).fetchone()
                    if row:
                        estimate = get_estimate(row["estimate_id"])
                        if estimate:
                            logger.info(f"Reply matched by conversation: {estimate['estimate_code']}")
        
        if not estimate:
            return
        
        # Store communication
        self._store_communication(email, estimate["id"], "received", results)
        
        # Update status
        self._update_after_reply(estimate, email)
    
    def _update_after_reply(self, estimate, email):
        """Update estimate after CLIENT reply (not our reply)"""
        comms = get_communications_for_estimate(estimate["id"])
        analysis = self.ai_analyzer.analyze_conversation(estimate, comms)
        
        status = analysis.get("status", "in_conversation")
        logger.info(f"  Status: {status}")
        
        reply_date = (email.get("receivedDateTime") or "")[:10]
        
        # Get our last sent date to compare
        our_last_sent = estimate.get("last_contact_date") or "1900-01-01"
        
        update_data = {
            "status": status,
        }
        
        # Only update last_contact_date if client replied AFTER our last send
        # (This prevents old client emails from messing up the timeline)
        if reply_date > our_last_sent:
            # Client replied after we sent - use subsequent days (10)
            if status in ["won", "lost"]:
                update_data["next_followup_date"] = None
                update_data["stop_followup"] = 1
            else:
                subsequent_days = int(get_setting("subsequent_followup_days", 10))
                next_date = datetime.strptime(reply_date, "%Y-%m-%d") + timedelta(days=subsequent_days)
                update_data["next_followup_date"] = next_date.strftime("%Y-%m-%d")
        # else: Client reply is older than our last send, don't change next_followup_date
        
        update_estimate(estimate["id"], update_data)
    
    def _generate_due_drafts(self, results):
        """Generate drafts for estimates that are due"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        for estimate in get_all_estimates():
            if estimate.get("status") in ["won", "lost"]:
                continue
            if estimate.get("stop_followup"):
                continue
            
            next_date = estimate.get("next_followup_date")
            if not next_date or next_date > today:
                continue
            
            # Check if draft exists
            followups = get_followups_for_estimate(estimate["id"])
            if any(f.get("status") in ["pending", "draft_ready"] for f in followups):
                continue
            
            # Generate
            logger.info(f"  Generating draft for {estimate['estimate_code']}...")
            try:
                engine = self._get_followup_engine()
                result = engine.generate_draft(estimate["id"])
                if result.get("success"):
                    results["drafts_generated"] += 1
            except Exception as e:
                logger.error(f"  Draft error: {e}")
    
    def _store_communication(self, email, estimate_id, direction, results):
        """Store communication record"""
        date_field = "sentDateTime" if direction == "sent" else "receivedDateTime"
        
        create_communication({
            "estimate_id": estimate_id,
            "email_id": email.get("id"),
            "conversation_id": email.get("conversationId"),
            "direction": direction,
            "subject": email.get("subject"),
            "body_preview": (email.get("bodyPreview") or "")[:500],
            "from_email": email.get("from", {}).get("emailAddress", {}).get("address"),
            "to_email": email.get("toRecipients", [{}])[0].get("emailAddress", {}).get("address") if email.get("toRecipients") else None,
            "email_date": email.get(date_field),
            "has_attachment": 1 if email.get("hasAttachments") else 0
        })
        results["new_communications"] += 1
    
    def _extract_pdf(self, message_id):
        """Extract data from PDF attachment"""
        attachments = self.outlook.get_pdf_attachments(message_id)
        for att in attachments:
            content = att.get("contentBytes")
            if content:
                return self.pdf_extractor.extract_from_base64(content)
        return None
    
    # === Helpers ===
    
    def _is_estimate_email(self, subject):
        if not subject:
            return False
        return bool(re.search(SUBJECT_PATTERN, subject, re.IGNORECASE) and 
                   re.search(ESTIMATE_CODE_PATTERN, subject))
    
    def _extract_estimate_code(self, text):
        """
        Extract estimate code and normalize it.
        Handles variations like: 25C-298, 25C298, 25C 298, 25C-298-A, 25C298A, 25C-298-A-R, etc.
        Returns the GROUP KEY (base + contractor, without revision)
        """
        if not text:
            return None
        
        # Pattern: base code, then optionally contractor letter (immediately after), then optionally revision
        # The contractor letter must be right after the number (with only spaces/dashes)
        # Pattern breakdown:
        # (2[4-9][CRcr]) - prefix like 25C or 25R
        # [\s\-]* - optional spaces/dashes
        # (\d{3}) - three digit number
        # (?:[\s\-]*([A-Za-z])(?=[\s\-]|$|R|Rev))? - optional contractor letter (not followed by more letters)
        # [\s\-]* - optional spaces/dashes  
        # (Rev\.?i?s?e?d?|R(?=\d|[\s\-]|$))? - revision marker
        
        # First, extract just the estimate code part (before any description)
        # Look for pattern at start or after "Estimate" 
        code_pattern = r'(?:Estimate[:\s\-]*)?(\d{2}[CRcr])[\s\-]*(\d{3})[\s\-]*([A-Za-z])?[\s\-]*(Rev\.?i?s?e?d?|R)?(?:[\s\-]*(\d))?(?=[\s\-]|$|[^A-Za-z0-9])'
        
        m = re.search(code_pattern, text, re.IGNORECASE)
        if not m:
            return None
        
        prefix = m.group(1).upper()  # 25C
        number = m.group(2)           # 298
        letter = m.group(3)           # A, B, C, or R, or None
        rev_marker = m.group(4)       # Rev, Revised, R, or None
        
        base_code = f"{prefix}-{number}"
        
        # Determine if letter is contractor or revision
        contractor = None
        
        if letter:
            letter = letter.upper()
            # If letter is R and there's no separate rev_marker, it's revision
            if letter == 'R':
                # R alone or R followed by rev_marker = revision, not contractor
                pass  # Don't set contractor
            else:
                # A, B, C, etc. = contractor
                contractor = letter
        
        # Build group key (without revision info)
        if contractor:
            group_key = f"{base_code}-{contractor}"
        else:
            group_key = base_code
        
        return group_key
    
    def _parse_estimate_code_full(self, text):
        """
        Parse estimate code and return all parts.
        Returns: {"group_key": "25C-298-A", "display_code": "25C-298-A-R", "base": "25C-298", "contractor": "A", "is_revision": True}
        """
        if not text:
            return None
        
        code_pattern = r'(?:Estimate[:\s\-]*)?(\d{2}[CRcr])[\s\-]*(\d{3})[\s\-]*([A-Za-z])?[\s\-]*(Rev\.?i?s?e?d?|R)?(?:[\s\-]*(\d))?(?=[\s\-]|$|[^A-Za-z0-9])'
        
        m = re.search(code_pattern, text, re.IGNORECASE)
        if not m:
            return None
        
        prefix = m.group(1).upper()
        number = m.group(2)
        letter = m.group(3)
        rev_marker = m.group(4)
        rev_num = m.group(5)
        
        base_code = f"{prefix}-{number}"
        
        contractor = None
        is_revision = False
        
        if letter:
            letter = letter.upper()
            if letter == 'R':
                is_revision = True
            else:
                contractor = letter
        
        if rev_marker:
            is_revision = True
        
        # Build group key (for database lookups - no revision)
        if contractor:
            group_key = f"{base_code}-{contractor}"
        else:
            group_key = base_code
        
        # Build display code (full code shown to user)
        display_code = group_key
        if is_revision:
            if rev_marker and rev_num:
                display_code += f"-{rev_marker.capitalize()}{rev_num}"
            elif rev_marker:
                display_code += f"-{rev_marker.capitalize()}"
            elif letter and letter == 'R':
                display_code += "-R"
        
        return {
            "group_key": group_key,
            "display_code": display_code,
            "base": base_code,
            "contractor": contractor,
            "is_revision": is_revision
        }
    
    def _parse_subject(self, subject):
        result = {}
        clean = re.sub(r'^(RE:\s*|FW:\s*)*Estimate\s*-?\s*', '', subject, flags=re.IGNORECASE).strip()
        clean = re.sub(ESTIMATE_CODE_PATTERN, '', clean).strip()
        clean = re.sub(r'^[-\s]+', '', clean).strip()
        
        parts = [p.strip() for p in clean.split(' - ') if p.strip()]
        if parts:
            result["gc_company"] = parts[0]
        if len(parts) > 1:
            last = parts[-1]
            if ',' in last:
                p = last.split(',', 1)
                result["project_name"] = p[0].strip()
                result["project_address"] = p[1].strip()
            else:
                result["project_name"] = last
        return result


# Singleton
_scanner = None
def get_email_scanner():
    global _scanner
    if _scanner is None:
        _scanner = EmailScanner()
    return _scanner
