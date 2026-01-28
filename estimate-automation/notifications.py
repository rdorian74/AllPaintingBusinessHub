"""
Notifications - Windows toast notifications
"""
import subprocess
import sys


class WindowsNotifier:
    """Send Windows toast notifications"""
    
    def __init__(self):
        self.app_name = "Estimate Automation"
    
    def notify(self, title, message, on_click=None):
        """
        Send a Windows toast notification
        
        Args:
            title: Notification title
            message: Notification message
            on_click: Optional callback or URL when clicked
        """
        try:
            # Try using win10toast if available
            self._notify_win10toast(title, message)
        except ImportError:
            # Fall back to PowerShell
            self._notify_powershell(title, message)
    
    def _notify_win10toast(self, title, message):
        """Use win10toast library"""
        from win10toast import ToastNotifier
        
        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            duration=10,
            threaded=True
        )
    
    def _notify_powershell(self, title, message):
        """Use PowerShell for notification"""
        # Escape special characters
        title = title.replace("'", "''").replace('"', '`"')
        message = message.replace("'", "''").replace('"', '`"')
        
        ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast>
    <visual>
        <binding template="ToastText02">
            <text id="1">{title}</text>
            <text id="2">{message}</text>
        </binding>
    </visual>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Estimate Automation").Show($toast)
'''
        
        try:
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                timeout=10
            )
        except Exception as e:
            # If PowerShell fails, try basic message box
            self._notify_messagebox(title, message)
    
    def _notify_messagebox(self, title, message):
        """Fallback: Use Windows message box"""
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)  # MB_ICONINFORMATION
        except:
            # Last resort: just print to console
            print(f"\n🔔 NOTIFICATION: {title}")
            print(f"   {message}\n")
    
    def notify_success(self, estimate_code, pdf_path=None, auto_sent=False, to_email=None):
        """
        Notify that an estimate was processed successfully
        
        Args:
            estimate_code: The estimate code
            pdf_path: Path to the generated PDF (optional)
            auto_sent: Whether the email was sent automatically (AI Agent auto mode)
            to_email: The recipient email (if auto_sent)
        """
        if auto_sent:
            title = f"📤 Estimate {estimate_code} SENT"
            if to_email:
                message = f"Email sent automatically to {to_email}"
            else:
                message = "Email sent automatically to client"
        else:
            title = f"✅ Estimate {estimate_code} Processed"
            message = "PDF generated and email draft created. Check your Drafts folder."
        
        self.notify(title, message)
    
    def notify_error(self, estimate_code, error):
        """Notify that an estimate processing failed"""
        title = f"❌ Estimate {estimate_code} Failed"
        message = f"Error: {error[:100]}"  # Truncate long errors
        self.notify(title, message)
    
    def notify_new_email(self, estimate_code):
        """Notify that a new estimate email was detected"""
        title = f"📧 New Estimate: {estimate_code}"
        message = "Processing started..."
        self.notify(title, message)
    
    def notify_ai_agent_issue(self, estimate_code, issues):
        """
        Notify that AI Agent found issues with an estimate
        
        Args:
            estimate_code: The estimate code
            issues: List of issues found or string description
        """
        title = f"⚠️ Review Needed: {estimate_code}"
        
        if isinstance(issues, list):
            issues_str = "; ".join(issues)
        else:
            issues_str = str(issues)
        
        message = f"AI Agent issues: {issues_str[:100]}"
        self.notify(title, message)


# Test notifications if run directly
if __name__ == "__main__":
    print("Testing Windows Notifications...")
    
    notifier = WindowsNotifier()
    
    # Test regular notification
    notifier.notify(
        "Test Notification",
        "This is a test from the Estimate Automation system."
    )
    
    # Test auto-sent notification
    notifier.notify_success("25C-999", auto_sent=True, to_email="test@example.com")
    
    print("Notifications sent!")
