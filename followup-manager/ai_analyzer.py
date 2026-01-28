"""
Follow Up Manager - AI Analyzer
Simple AI for draft generation and conversation analysis
"""
import json
import re
import logging

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, EMAIL_SIGNATURE

logger = logging.getLogger(__name__)

class AIAnalyzer:
    def __init__(self):
        if Anthropic is None:
            raise ImportError("anthropic required")
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
    
    def _call_claude(self, prompt, max_tokens=500):
        """Make Claude API call"""
        try:
            resp = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude error: {e}")
            return None
    
    def analyze_conversation(self, estimate, communications):
        """
        Analyze conversation to determine status.
        Returns: {"status": "waiting|in_conversation|won|lost"}
        """
        if not communications:
            return {"status": "waiting"}
        
        # Build conversation summary
        conv = []
        for c in communications[-5:]:  # Last 5 only
            direction = "SENT" if c.get("direction") == "sent" else "RECEIVED"
            preview = (c.get("body_preview") or "")[:300]
            conv.append(f"{direction}: {preview}")
        
        prompt = f"""Analyze this email conversation about a painting estimate.

CONVERSATION:
{chr(10).join(conv)}

What is the status? Choose ONE:
- "won" = Client clearly awarded/approved the project
- "lost" = Client clearly rejected/went elsewhere  
- "in_conversation" = Client responded but no decision yet
- "waiting" = No client response

Return ONLY JSON: {{"status": "waiting"}}"""

        result = self._call_claude(prompt, 100)
        
        if result:
            try:
                m = re.search(r'\{[^}]+\}', result)
                if m:
                    data = json.loads(m.group(0))
                    if data.get("status") in ["waiting", "in_conversation", "won", "lost"]:
                        return data
            except:
                pass
        
        return {"status": "waiting"}
    
    def generate_followup_draft(self, estimate, communications, followup_number):
        """
        Generate a simple follow-up email with HTML formatting.
        Returns: {"subject": "...", "body": "..."}
        """
        contact = estimate.get("contact_name", "")
        project = estimate.get("project_name") or estimate.get("gc_company", "your project")
        code = estimate.get("estimate_code", "")
        contact_email = estimate.get("contact_email", "")
        last_contact = estimate.get("last_contact_date", "")
        
        # Greeting - try contact_name first, then extract from email
        if contact:
            first_name = contact.split()[0]
            greeting = f"Hi {first_name},"
        elif contact_email and "@" in contact_email:
            email_name = contact_email.split("@")[0]
            email_name = ''.join(c for c in email_name if not c.isdigit())
            if "." in email_name:
                first_name = email_name.split(".")[0]
            elif "_" in email_name:
                first_name = email_name.split("_")[0]
            else:
                first_name = email_name
            first_name = first_name.capitalize()
            if len(first_name) >= 2:
                greeting = f"Hi {first_name},"
            else:
                greeting = "Hello,"
        else:
            greeting = "Hello,"
        
        # Check if estimate is older than 4 months (120 days)
        is_old_estimate = False
        if last_contact:
            try:
                from datetime import datetime
                last_date = datetime.strptime(last_contact, "%Y-%m-%d")
                days_old = (datetime.now() - last_date).days
                is_old_estimate = days_old >= 120
            except:
                pass
        
        if is_old_estimate:
            prompt = f"""Write a polite follow-up email for a painting estimate that was sent MORE THAN 4 MONTHS AGO.

Contact: {contact or 'Unknown'}
Project: {project}

TONE: Courteous, non-pushy, appreciative of their time

CONTENT:
- Acknowledge the estimate has been open for several months
- Kindly ask if the project moved forward
- Politely ask if another contractor was selected
- If they chose someone else, request brief feedback on how close our estimate was
- Explain this helps us calibrate pricing and improve service
- NO signature (added automatically)

Start with: {greeting}

EXAMPLE MESSAGES:

Example 1: "I hope you're doing well. I wanted to reach out regarding the estimate we provided for your project some time ago. I understand that project timelines can shift, and I was curious whether things have moved forward or if plans have changed. If you've already selected another contractor, I completely understand—these decisions involve many factors. If you have a moment, I'd really appreciate any brief feedback on how our pricing compared. It helps us stay competitive and better serve future clients. Thank you so much for your time."

Example 2: "I hope this message finds you well. I'm reaching out about the estimate we sent a few months back. I wanted to check in and see if the project is still on your radar or if circumstances have changed. If you ended up going with another contractor, no worries at all. I'd be grateful for any quick feedback on our estimate—knowing how we compared helps us improve. Thanks again for considering us, and I wish you all the best."

Example 3: "I hope you're having a good day. I realized it's been a while since we sent over the estimate for your project, and I wanted to touch base. If the project moved forward with someone else, I completely understand. If you have a moment, I'd appreciate hearing how our estimate compared—it's valuable feedback that helps us improve. Thank you for your time and consideration."

Return ONLY the email body text, no subject line."""
        else:
            prompt = f"""Write a SHORT follow-up email for a painting estimate.

Contact: {contact or 'Unknown'}
Project: {project}
Follow-up #: {followup_number}

RULES:
- Maximum 3-4 sentences
- Warm, friendly and professional
- DO NOT mention prices or amounts
- DO NOT be pushy or aggressive
- Offer to help with questions or clarifications
- NO signature (added automatically)

Start with: {greeting}

EXAMPLE MESSAGES (use as inspiration, vary the wording):

Example 1: "I hope you're having a good day. I just wanted to follow up on the estimate we sent over for your project. Whenever you have a moment to review it, feel free to let me know if anything needs clarification or if you'd like to go over any part together. I'm here to help and make things easy for you."

Example 2: "I hope you're doing well today. I'm checking in regarding the estimate we recently sent. If you have any questions, need more details, or would like to discuss any part of the scope, I'm more than happy to help. Thank you for considering us."

Example 3: "I hope you're having a great day. I wanted to reach out and see how things are going with the estimate we shared. Please don't hesitate to reach out if something needs adjusting, or if you'd like to walk through anything together."

Example 4: "I hope your day is going well. I'm touching base about the estimate we sent for your project. If you'd like to review anything in more detail or have questions about the scope or materials, I'm always available to help."

Example 5: "I hope you're having a nice day. I wanted to gently follow up on the estimate we prepared for you. Whenever you're ready, feel free to reach out with any questions or updates. I'm here to support you with whatever you need moving forward."

Return ONLY the email body text, no subject line."""

        result = self._call_claude(prompt, 400)
        
        if result:
            body = self._clean_body(result)
        else:
            # Fallback
            if is_old_estimate:
                body = f"""{greeting}

I hope you're doing well. I wanted to reach out regarding the estimate we provided for {project} some time ago. I understand projects can shift in timing, and I was wondering if you had any updates.

If you've already selected another contractor, I completely understand. If you have a moment, I'd appreciate any brief feedback on how our estimate compared—it helps us stay competitive and improve our service.

Thank you for your time."""
            else:
                body = f"""{greeting}

I hope you're having a good day. I just wanted to follow up on the estimate we sent over for {project}. Feel free to let me know if anything needs clarification.

I'm here to help and make things easy for you."""
        
        # Convert to HTML with proper formatting
        body_html = self._format_html(body)
        
        return {"subject": f"RE: Estimate {code} - {project}", "body": body_html}
    
    def _format_html(self, text):
        """Convert plain text to professional HTML email"""
        # Convert newlines to <br>
        html_body = text.replace("\n", "<br>")
        
        # Build full HTML with signature
        signature_html = EMAIL_SIGNATURE.replace("\n", "<br>")
        
        html = f"""<div style="font-family: Arial, sans-serif; font-size: 13pt; color: #000000;">
{html_body}
<br><br>
{signature_html}
</div>"""
        
        return html
    
    def _clean_body(self, text):
        """Remove any signature AI might have added"""
        lines = text.split('\n')
        markers = ['regards', 'best', 'thanks', 'sincerely', 'rod rivas', 'all painting']
        
        for i, line in enumerate(lines):
            if any(m in line.lower() for m in markers):
                return '\n'.join(lines[:i]).strip()
        
        return text.strip()


# Singleton
_analyzer = None
def get_ai_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = AIAnalyzer()
    return _analyzer
