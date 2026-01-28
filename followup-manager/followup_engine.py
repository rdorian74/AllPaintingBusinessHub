"""
Follow Up Manager - Follow-up Engine
Generates follow-up drafts with email thread history
"""
import logging
from datetime import datetime, timedelta

from database import (
    get_estimate, update_estimate,
    get_communications_for_estimate, get_followups_for_estimate,
    create_followup, update_followup, get_setting
)
from outlook_client import get_outlook_client
from ai_analyzer import get_ai_analyzer
from config import MAX_FOLLOWUPS_BEFORE_ALERT, MONITORED_EMAIL

logger = logging.getLogger(__name__)

class FollowupEngine:
    def __init__(self):
        self.outlook = get_outlook_client()
        self.ai = get_ai_analyzer()
    
    def generate_draft(self, estimate_id):
        """Generate follow-up draft with thread history"""
        estimate = get_estimate(estimate_id)
        if not estimate:
            return {"error": "Not found"}
        
        code = estimate.get("estimate_code")
        logger.info(f"Generating draft for {code}...")
        
        # Get communications
        comms = get_communications_for_estimate(estimate_id)
        
        # Get original message ID for threading
        original_id = estimate.get("original_message_id")
        if not original_id:
            # Try to find from communications
            for c in reversed(comms):
                if c.get("direction") == "sent" and c.get("email_id"):
                    original_id = c.get("email_id")
                    break
        
        # Determine follow-up number
        followup_num = estimate.get("followup_count", 0) + 1
        
        # Generate content via AI
        draft = self.ai.generate_followup_draft(estimate, comms, followup_num)
        
        # Create Outlook draft
        outlook_id = None
        method = "none"
        
        try:
            result = self.outlook.create_threaded_draft(
                to_email=estimate.get("contact_email"),
                subject=draft.get("subject"),
                body_html=draft.get("body"),  # Already HTML from AI analyzer
                original_message_id=original_id,
                use_followup_folder=True
            )
            outlook_id = result.get("id")
            method = result.get("method", "unknown")
            logger.info(f"  Draft created: {method}")
        except Exception as e:
            logger.error(f"  Outlook error: {e}")
        
        # Store in database
        followup_id = create_followup({
            "estimate_id": estimate_id,
            "followup_number": followup_num,
            "scheduled_date": datetime.now().strftime("%Y-%m-%d"),
            "draft_content": draft.get("body"),
            "draft_subject": draft.get("subject"),
            "outlook_draft_id": outlook_id,
            "status": "draft_ready" if outlook_id else "pending"
        })
        
        return {
            "success": True,
            "followup_id": followup_id,
            "outlook_draft_id": outlook_id,
            "method": method
        }
    
    def check_sent_drafts(self):
        """Check if drafts have been sent"""
        from database import get_connection
        
        sent = []
        
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT f.*, e.estimate_code FROM followups f
                JOIN estimates e ON f.estimate_id = e.id
                WHERE f.status = 'draft_ready' AND f.outlook_draft_id IS NOT NULL
            """).fetchall()
        
        for row in rows:
            row = dict(row)
            # If draft is gone, it was sent
            draft = self.outlook.get_draft(row["outlook_draft_id"])
            if not draft:
                self._mark_sent(row)
                sent.append(row["estimate_code"])
        
        return sent
    
    def _mark_sent(self, followup):
        """Mark followup as sent"""
        now = datetime.now()
        update_followup(followup["id"], {
            "status": "sent",
            "sent_at": now.isoformat()
        })
        
        # Update estimate
        estimate = get_estimate(followup["estimate_id"])
        if estimate:
            count = estimate.get("followup_count", 0) + 1
            subsequent = int(get_setting("subsequent_followup_days", 10))
            next_date = now + timedelta(days=subsequent)
            
            update_estimate(followup["estimate_id"], {
                "followup_count": count,
                "last_contact_date": now.strftime("%Y-%m-%d"),
                "next_followup_date": next_date.strftime("%Y-%m-%d")
            })
            
            # Alert if too many
            if count >= MAX_FOLLOWUPS_BEFORE_ALERT:
                self._send_alert(estimate)
    
    def _send_alert(self, estimate):
        """Send alert for too many follow-ups"""
        try:
            self.outlook.send_email(
                MONITORED_EMAIL,
                f"Review: {estimate['estimate_code']} - Multiple follow-ups",
                f"<p>Estimate {estimate['estimate_code']} has {estimate.get('followup_count')} follow-ups.</p>"
                f"<p>Client: {estimate.get('gc_company')}</p>"
            )
        except Exception as e:
            logger.error(f"Alert error: {e}")
    
    def delay_followup(self, estimate_id, days):
        """Delay follow-up by days"""
        estimate = get_estimate(estimate_id)
        if not estimate:
            return {"error": "Not found"}
        
        current = estimate.get("next_followup_date") or datetime.now().strftime("%Y-%m-%d")
        new_date = datetime.strptime(current, "%Y-%m-%d") + timedelta(days=days)
        update_estimate(estimate_id, {"next_followup_date": new_date.strftime("%Y-%m-%d")})
        return {"success": True, "new_date": new_date.strftime("%Y-%m-%d")}
    
    def stop_followups(self, estimate_id):
        """Stop follow-ups for estimate"""
        update_estimate(estimate_id, {"stop_followup": 1})
        return {"success": True}
    
    def resume_followups(self, estimate_id):
        """Resume follow-ups"""
        subsequent = int(get_setting("subsequent_followup_days", 10))
        next_date = datetime.now() + timedelta(days=subsequent)
        update_estimate(estimate_id, {
            "stop_followup": 0,
            "next_followup_date": next_date.strftime("%Y-%m-%d")
        })
        return {"success": True}


# Singleton
_engine = None
def get_followup_engine():
    global _engine
    if _engine is None:
        _engine = FollowupEngine()
    return _engine
