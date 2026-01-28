"""
Calendar Manager for Follow Up Manager
Handles calendar events for follow-up reminders
"""
from datetime import datetime, timedelta
from outlook_client import get_outlook_client

class CalendarManager:
    """Manages Outlook calendar events for follow-up reminders"""
    
    def __init__(self):
        self.outlook = get_outlook_client()
    
    def create_followup_reminder(self, estimate, followup_number, scheduled_date):
        """
        Create a calendar event for a follow-up
        
        Args:
            estimate: Estimate record
            followup_number: Which follow-up this is
            scheduled_date: Date to schedule (YYYY-MM-DD)
            
        Returns:
            Calendar event object or None
        """
        subject = f"Follow-up #{followup_number}: {estimate.get('estimate_code')} - {estimate.get('gc_company')}"
        
        body = f"""
        <h3>Follow-up Reminder</h3>
        <p><strong>Estimate:</strong> {estimate.get('estimate_code')}</p>
        <p><strong>Client:</strong> {estimate.get('gc_company')}</p>
        <p><strong>Contact:</strong> {estimate.get('contact_name', 'N/A')} ({estimate.get('contact_email', 'N/A')})</p>
        <p><strong>Project:</strong> {estimate.get('project_name')}</p>
        <p><strong>Location:</strong> {estimate.get('project_address', 'N/A')}</p>
        <p><strong>Amount:</strong> ${estimate.get('total_amount', 0):,.2f}</p>
        <p><strong>Follow-up #:</strong> {followup_number}</p>
        <hr>
        <p>Check the Follow Up Manager dashboard to review and send the draft.</p>
        """
        
        # Set event for 9 AM on the scheduled date
        start = f"{scheduled_date}T09:00:00"
        end = f"{scheduled_date}T09:30:00"
        
        try:
            return self.outlook.create_calendar_event(
                subject=subject,
                body=body,
                start_datetime=start,
                end_datetime=end,
                reminder_minutes=15
            )
        except Exception as e:
            print(f"Error creating calendar event: {e}")
            return None
    
    def update_followup_reminder(self, event_id, new_date, estimate=None, followup_number=None):
        """
        Update a follow-up calendar event
        
        Args:
            event_id: ID of the calendar event
            new_date: New date (YYYY-MM-DD)
            estimate: Optional estimate to update body
            followup_number: Optional new followup number
        """
        updates = {
            "start": {
                "dateTime": f"{new_date}T09:00:00",
                "timeZone": "Pacific Standard Time"
            },
            "end": {
                "dateTime": f"{new_date}T09:30:00",
                "timeZone": "Pacific Standard Time"
            }
        }
        
        if estimate and followup_number:
            updates["subject"] = f"Follow-up #{followup_number}: {estimate.get('estimate_code')} - {estimate.get('gc_company')}"
        
        try:
            return self.outlook.update_calendar_event(event_id, updates)
        except Exception as e:
            print(f"Error updating calendar event: {e}")
            return None
    
    def delete_event(self, event_id):
        """Delete a calendar event"""
        try:
            return self.outlook.delete_calendar_event(event_id)
        except Exception as e:
            print(f"Error deleting calendar event: {e}")
            return None
    
    def create_review_reminder(self, estimate, message):
        """
        Create a calendar event to review an estimate
        
        Args:
            estimate: Estimate record
            message: Custom message for the event
        """
        subject = f"Review: {estimate.get('estimate_code')} - {estimate.get('gc_company')}"
        
        body = f"""
        <h3>Estimate Review Reminder</h3>
        <p><strong>Estimate:</strong> {estimate.get('estimate_code')}</p>
        <p><strong>Client:</strong> {estimate.get('gc_company')}</p>
        <p><strong>Project:</strong> {estimate.get('project_name')}</p>
        <p><strong>Amount:</strong> ${estimate.get('total_amount', 0):,.2f}</p>
        <hr>
        <p>{message}</p>
        """
        
        # Schedule for tomorrow at 9 AM
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = f"{tomorrow}T09:00:00"
        end = f"{tomorrow}T09:30:00"
        
        try:
            return self.outlook.create_calendar_event(
                subject=subject,
                body=body,
                start_datetime=start,
                end_datetime=end,
                reminder_minutes=60
            )
        except Exception as e:
            print(f"Error creating review reminder: {e}")
            return None

# Singleton instance
_manager = None

def get_calendar_manager():
    """Get or create the calendar manager instance"""
    global _manager
    if _manager is None:
        _manager = CalendarManager()
    return _manager
