"""
Main - Entry point for the Estimate Automation System
All Painting Ltd.
"""
import time
import threading
import requests
from datetime import datetime
import config
from email_monitor import EmailMonitor
from estimate_processor import EstimateProcessor
from draft_creator import DraftCreator
from database import Database
from notifications import WindowsNotifier


# Initialize components
email_monitor = EmailMonitor()
processor = EstimateProcessor()
draft_creator = DraftCreator()
db = Database()
notifier = WindowsNotifier()


# =============================================================================
# AI AGENT FUNCTIONS (NEW)
# =============================================================================

def call_ai_agent(pdf_path, extracted_data, estimate_code, word_path=None):
    """
    Call the AI Agent API to validate the PDF
    
    Args:
        pdf_path: Path to the generated PDF
        extracted_data: Data extracted from the estimate
        estimate_code: The estimate code (e.g., 25C-319)
        word_path: Path to the original Word document (for comparison)
    
    Returns:
        Dictionary with validation result:
        {
            "success": True/False,
            "passed": True/False,
            "issues": ["list of issues"],
            "confidence_score": 0-100,
            "cost": 0.00,
            "action_recommended": "send" | "draft" | "review",
            "attempts": 1,
            "auto_corrected": False
        }
    """
    if not config.AI_AGENT_ENABLED:
        return {
            "success": True,
            "passed": True,
            "issues": [],
            "confidence_score": 100,
            "cost": 0,
            "action_recommended": "draft",
            "skipped": True,
            "message": "AI Agent disabled"
        }
    
    try:
        print(f"   🤖 Calling AI Agent for validation...")
        
        payload = {
            "pdf_path": pdf_path,
            "extracted_data": extracted_data,
            "estimate_code": estimate_code
        }
        
        # Include word_path for Word vs PDF comparison
        if word_path:
            payload["word_path"] = word_path
            print(f"   📄 Including Word document for comparison")
        
        response = requests.post(
            config.AI_AGENT_API_URL,
            json=payload,
            timeout=config.AI_AGENT_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Log auto-correction if it happened
            if result.get("auto_corrected"):
                print(f"   🔄 AI Agent auto-corrected the PDF after {result.get('attempts')} attempts")
            
            print(f"   🤖 AI Agent response: passed={result.get('passed')}, confidence={result.get('confidence_score')}%")
            return {
                "success": True,
                **result
            }
        else:
            error_msg = f"AI Agent returned status {response.status_code}: {response.text}"
            print(f"   ⚠️ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
    
    except requests.exceptions.Timeout:
        error_msg = "AI Agent request timed out"
        print(f"   ⚠️ {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }
    
    except requests.exceptions.ConnectionError:
        error_msg = "Could not connect to AI Agent (is it running on port 5011?)"
        print(f"   ⚠️ {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }
    
    except Exception as e:
        error_msg = f"AI Agent error: {str(e)}"
        print(f"   ⚠️ {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }


def send_estimate_email(pdf_path, pdf_filename, extracted_data, estimate_code):
    """
    Send the estimate email directly (used in auto mode)
    
    Args:
        pdf_path: Path to the PDF file
        pdf_filename: Name of the PDF file
        extracted_data: Data extracted from the estimate
        estimate_code: The estimate code
    
    Returns:
        Dictionary with result
    """
    from outlook_client import OutlookClient
    
    # Extract client info (same logic as draft_creator)
    client_info = extracted_data.get("client_info", {})
    client_email = client_info.get("email", "")
    
    if client_email and "/" in client_email:
        client_email = client_email.split("/")[0].strip()
    
    if not client_email or "@" not in client_email:
        return {
            "success": False,
            "error": "Could not find valid client email"
        }
    
    # Get contact name
    contact = client_info.get("contact_person", "")
    if contact and "/" in contact:
        contact = contact.split("/")[0].strip()
    contact_name = contact.split()[0] if contact else None
    
    # Get project info
    project_info = extracted_data.get("project_info", {})
    project_name = project_info.get("name", "")
    project_address = project_info.get("address", "")
    project_city = project_info.get("city_province_postal", "")
    
    full_address = project_address
    if project_city:
        full_address = f"{project_address} in {project_city}" if project_address else project_city
    
    # Generate subject
    subject = pdf_filename
    if subject.startswith("Estimate - "):
        subject = "Estimate - " + subject[11:]
    if subject.lower().endswith(".pdf"):
        subject = subject[:-4]
    
    # Generate email body (same as draft_creator)
    greeting = f"Hi {contact_name}," if contact_name else "Hello,"
    
    if project_name and full_address:
        project_desc = f"the {project_name} project located at {full_address}"
    elif project_name:
        project_desc = f"the {project_name} project"
    elif full_address:
        project_desc = f"the project located at {full_address}"
    else:
        project_desc = "your project"
    
    body_html = f"""
<html>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
<p>{greeting}</p>

<p>Please find attached our estimate <strong>{estimate_code}</strong> for {project_desc}.</p>

<p>Thank you for the opportunity to provide this quotation. We would be pleased to discuss any aspects of the scope or pricing at your convenience.</p>

<p>Should you have any questions or require any adjustments to the proposal, please don't hesitate to reach out—we're happy to assist.</p>

<p>We look forward to the opportunity to work with you on this project.</p>

<p>Best regards,</p>

<p><strong>All Painting Ltd.</strong><br>
Phone: (604) 525-1403<br>
Email: info@allpaintingltd.com<br>
www.allpaintingltd.com</p>
</body>
</html>
"""
    
    try:
        outlook = OutlookClient()
        result = outlook.send_email_with_attachment(
            to_email=client_email,
            subject=subject,
            body_html=body_html,
            attachment_path=pdf_path
        )
        
        return {
            "success": True,
            "to_email": client_email,
            "subject": subject,
            "message": "Email sent successfully"
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# =============================================================================
# MAIN PROCESSING FUNCTIONS
# =============================================================================

def process_estimate_by_code(estimate_code):
    """
    Process an estimate by code (used for manual processing)
    
    Args:
        estimate_code: The estimate code (e.g., 25C-325)
    
    Returns:
        Dictionary with result
    """
    print(f"\n{'='*60}")
    print(f"MANUAL PROCESSING: {estimate_code}")
    print(f"{'='*60}")
    
    # Add to database
    db_id = db.add_estimate(
        estimate_code=estimate_code,
        email_subject="Manual Processing"
    )
    db.add_log(db_id, "start", "info", "Manual processing started")
    
    # Create estimate info
    estimate_info = {
        "code": estimate_code,
        "code_variants": email_monitor.normalize_estimate_code(estimate_code)
    }
    
    # Process the estimate
    result = process_single_estimate(estimate_info, db_id)
    
    return result


def process_single_estimate(estimate_info, db_id=None):
    """
    Process a single estimate
    
    Args:
        estimate_info: Dictionary with estimate code and variants
        db_id: Database ID for the estimate (optional)
    
    Returns:
        Dictionary with result
    """
    code = estimate_info["code"]
    word_path = None  # Will be set in Step 1
    
    try:
        # Step 1: Find Word document
        print(f"\n📁 Step 1: Finding Word document...")
        word_path = processor.find_word_document(estimate_info.get("code_variants", code))
        
        if not word_path:
            error_msg = f"Word document not found for {code}"
            if db_id:
                db.update_estimate(db_id, status="error", error_message=error_msg)
                db.add_log(db_id, "find_word", "error", error_msg)
            notifier.notify_error(code, error_msg)
            return {"success": False, "error": error_msg}
        
        if db_id:
            db.update_estimate(db_id, word_file_path=word_path)
            db.add_log(db_id, "find_word", "success", f"Found: {word_path}")
        
        # Step 2: Generate PDF
        print(f"\n📄 Step 2: Generating PDF...")
        pdf_result = processor.generate_pdf(word_path)
        
        if not pdf_result.get("success"):
            error_msg = pdf_result.get("error", "Unknown error generating PDF")
            if db_id:
                db.update_estimate(db_id, status="error", error_message=error_msg)
                db.add_log(db_id, "generate_pdf", "error", error_msg)
            notifier.notify_error(code, error_msg)
            return {"success": False, "error": error_msg}
        
        pdf_path = pdf_result.get("pdf_path")
        pdf_filename = pdf_result.get("pdf_filename")
        extracted_data = pdf_result.get("extracted_data", {})
        
        if db_id:
            db.update_estimate(db_id, pdf_file_path=pdf_path)
            db.add_log(db_id, "generate_pdf", "success", f"Generated: {pdf_filename}")
        
        # =====================================================================
        # Step 2.5: AI AGENT VALIDATION (NEW - with Word comparison)
        # =====================================================================
        print(f"\n🤖 Step 2.5: AI Agent Validation...")
        
        # Pass word_path for Word vs PDF comparison
        agent_result = call_ai_agent(pdf_path, extracted_data, code, word_path)
        
        if db_id:
            log_msg = f"AI Agent: passed={agent_result.get('passed')}, confidence={agent_result.get('confidence_score', 'N/A')}%"
            if agent_result.get('auto_corrected'):
                log_msg += f" (auto-corrected after {agent_result.get('attempts')} attempts)"
            db.add_log(db_id, "ai_agent", "info", log_msg)
        
        # Handle AI Agent failure
        if not agent_result.get("success"):
            if config.AI_AGENT_FALLBACK_TO_DRAFT:
                print(f"   ⚠️ AI Agent unavailable, falling back to draft creation")
                if db_id:
                    db.add_log(db_id, "ai_agent", "warning", 
                        f"AI Agent unavailable: {agent_result.get('error')}. Falling back to draft.")
            else:
                error_msg = f"AI Agent error: {agent_result.get('error')}"
                if db_id:
                    db.update_estimate(db_id, status="error", error_message=error_msg)
                    db.add_log(db_id, "ai_agent", "error", error_msg)
                notifier.notify_error(code, error_msg)
                return {"success": False, "error": error_msg}
        
        # Handle validation failure (issues found)
        elif not agent_result.get("passed", True):
            issues = agent_result.get("issues", ["Unknown issue"])
            issues_str = "; ".join(issues)
            
            print(f"   ⚠️ AI Agent found issues: {issues_str}")
            
            if db_id:
                db.update_estimate(db_id, status="needs_review", 
                    error_message=f"AI Agent issues: {issues_str}")
                db.add_log(db_id, "ai_agent", "warning", f"Validation failed: {issues_str}")
            
            # Notify Rodrigo about the issues
            notifier.notify_error(code, f"AI Agent found issues: {issues_str}")
            
            return {
                "success": False,
                "needs_review": True,
                "pdf_path": pdf_path,
                "issues": issues,
                "error": f"AI Agent validation failed: {issues_str}"
            }
        
        # Check if PDF was auto-corrected (might have new path)
        if agent_result.get("auto_corrected"):
            # The PDF might have been regenerated, update the path
            new_pdf_path = agent_result.get("pdf_path")
            if new_pdf_path and new_pdf_path != pdf_path:
                pdf_path = new_pdf_path
                if db_id:
                    db.update_estimate(db_id, pdf_file_path=pdf_path)
                    db.add_log(db_id, "ai_agent", "info", f"PDF auto-corrected: {pdf_path}")
        
        # AI Agent passed - decide between draft or send
        if config.AI_AGENT_MODE == "auto" and agent_result.get("passed", False):
            # AUTO MODE: Send email directly
            print(f"\n📤 Step 3 (Auto): Sending email directly...")
            
            send_result = send_estimate_email(pdf_path, pdf_filename, extracted_data, code)
            
            if not send_result.get("success"):
                error_msg = send_result.get("error", "Unknown error sending email")
                if db_id:
                    db.update_estimate(db_id, status="error", error_message=f"Send failed: {error_msg}")
                    db.add_log(db_id, "send_email", "error", error_msg)
                notifier.notify_error(code, f"Auto-send failed: {error_msg}")
                return {"success": False, "error": error_msg}
            
            if db_id:
                db.update_estimate(
                    db_id,
                    status="sent",
                    draft_to_email=send_result.get("to_email"),
                    draft_subject=send_result.get("subject")
                )
                db.add_log(db_id, "send_email", "success", 
                    f"Email sent automatically to {send_result.get('to_email')}")
            
            # Success - email sent!
            print(f"\n✅ ESTIMATE {code} SENT AUTOMATICALLY!")
            print(f"   📬 To: {send_result.get('to_email')}")
            notifier.notify_success(code, pdf_path, auto_sent=True, 
                to_email=send_result.get("to_email"))
            
            return {
                "success": True,
                "auto_sent": True,
                "estimate_code": code,
                "pdf_path": pdf_path,
                "sent_to": send_result.get("to_email"),
                "subject": send_result.get("subject")
            }
        
        # =====================================================================
        # Step 3: Create draft email (REVIEW MODE or fallback)
        # =====================================================================
        print(f"\n📧 Step 3: Creating email draft...")
        draft_result = draft_creator.create_estimate_draft(
            pdf_path=pdf_path,
            pdf_filename=pdf_filename,
            extracted_data=extracted_data,
            estimate_code=code
        )
        
        if not draft_result.get("success"):
            # PDF was generated but draft failed - partial success
            error_msg = draft_result.get("error", "Unknown error creating draft")
            if db_id:
                db.update_estimate(db_id, status="partial", error_message=f"PDF ok, draft failed: {error_msg}")
                db.add_log(db_id, "create_draft", "error", error_msg)
            notifier.notify_error(code, f"PDF generated but draft failed: {error_msg}")
            return {
                "success": False,
                "partial": True,
                "pdf_path": pdf_path,
                "error": error_msg
            }
        
        if db_id:
            db.update_estimate(
                db_id,
                status="completed",
                draft_id=draft_result.get("draft_id"),
                draft_to_email=draft_result.get("to_email"),
                draft_subject=draft_result.get("subject")
            )
            db.add_log(db_id, "create_draft", "success", f"Draft created for {draft_result.get('to_email')}")
        
        # Success!
        print(f"\n✅ ESTIMATE {code} PROCESSED SUCCESSFULLY!")
        notifier.notify_success(code, pdf_path)
        
        return {
            "success": True,
            "estimate_code": code,
            "pdf_path": pdf_path,
            "draft_to": draft_result.get("to_email"),
            "draft_subject": draft_result.get("subject")
        }
    
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Error processing {code}: {error_msg}")
        if db_id:
            db.update_estimate(db_id, status="error", error_message=error_msg)
            db.add_log(db_id, "process", "error", error_msg)
        notifier.notify_error(code, error_msg)
        return {"success": False, "error": error_msg}


def process_new_estimates():
    """
    Check for and process new estimate emails
    
    Returns:
        Number of estimates processed
    """
    print(f"\n🔍 Checking for new estimate emails...")
    
    # Check for new estimate emails
    new_estimates = email_monitor.check_for_new_estimates()
    
    if not new_estimates:
        print("   No new estimates found")
        return 0
    
    print(f"   Found {len(new_estimates)} new estimate(s)")
    
    processed = 0
    for estimate_info in new_estimates:
        code = estimate_info["code"]
        
        # Check if already in database
        if db.is_email_processed(estimate_info.get("email_id")):
            print(f"   ⏭️ {code} already processed, skipping")
            continue
        
        # Notify about new email
        notifier.notify_new_email(code)
        
        # Add to database
        db_id = db.add_estimate(
            estimate_code=code,
            email_id=estimate_info.get("email_id"),
            email_subject=estimate_info.get("subject"),
            email_received_at=estimate_info.get("received_at")
        )
        db.add_log(db_id, "email_detected", "info", f"Email from {estimate_info.get('sender')}")
        
        # Process the estimate
        result = process_single_estimate(estimate_info, db_id)
        
        if result.get("success"):
            processed += 1
    
    return processed


def monitoring_loop():
    """Main monitoring loop"""
    from dashboard import get_automation_state
    
    print(f"\n🔄 Monitoring loop started (checking every {config.CHECK_INTERVAL_SECONDS} seconds)")
    
    while True:
        state = get_automation_state()
        
        if not state["running"]:
            print("   Monitoring stopped")
            break
        
        if state["paused"]:
            print("   Monitoring paused, waiting...")
            time.sleep(10)
            continue
        
        try:
            process_new_estimates()
            state["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"   ❌ Error in monitoring loop: {e}")
        
        # Wait for next check
        time.sleep(config.CHECK_INTERVAL_SECONDS)


def start_monitoring_thread():
    """Start the monitoring thread"""
    from dashboard import get_automation_state
    
    state = get_automation_state()
    state["running"] = True
    state["paused"] = False
    
    thread = threading.Thread(target=monitoring_loop, daemon=True)
    thread.start()
    state["monitoring_thread"] = thread
    
    return thread


def main():
    """Main entry point"""
    print("\n" + "="*60)
    print("ALL PAINTING LTD - ESTIMATE AUTOMATION SYSTEM")
    print("="*60)
    print(f"Monitored email: {config.MONITORED_EMAIL}")
    print(f"Watching for emails from: {', '.join(config.IAN_EMAILS)}")
    print(f"Estimate folders: {', '.join(config.ESTIMATE_FOLDERS)}")
    print(f"Check interval: {config.CHECK_INTERVAL_SECONDS} seconds")
    print(f"Dashboard: http://localhost:{config.DASHBOARD_PORT}")
    
    # AI Agent status
    print("-"*60)
    if config.AI_AGENT_ENABLED:
        print(f"🤖 AI Agent: ENABLED")
        print(f"   Mode: {config.AI_AGENT_MODE.upper()}")
        print(f"   API: {config.AI_AGENT_API_URL}")
        print(f"   Features: Word vs PDF comparison, Auto-correction")
        if config.AI_AGENT_MODE == "auto":
            print(f"   ⚡ Auto-send is ON - emails will be sent automatically!")
        else:
            print(f"   📝 Review mode - drafts will be created for review")
    else:
        print(f"🤖 AI Agent: DISABLED (using original draft-only flow)")
    print("="*60)
    
    # Check if estimate generator is running
    if not processor.check_api_health():
        print("\n⚠️  WARNING: Estimate Generator API is not running!")
        print("   Please start it with: runestimatergenerator.bat")
        print("   The automation system will wait for it to be available.")
    
    # Check if AI Agent is running (if enabled)
    if config.AI_AGENT_ENABLED:
        try:
            response = requests.get(
                config.AI_AGENT_API_URL.replace("/validate", "/status"),
                timeout=5
            )
            if response.status_code == 200:
                print(f"\n✅ AI Agent is running")
                agent_status = response.json()
                if agent_status.get("auto_correction_enabled"):
                    print(f"   🔄 Auto-correction: ENABLED (max {agent_status.get('max_attempts', 3)} attempts)")
            else:
                print(f"\n⚠️  WARNING: AI Agent returned status {response.status_code}")
        except:
            print(f"\n⚠️  WARNING: AI Agent is not running on port 5011")
            if config.AI_AGENT_FALLBACK_TO_DRAFT:
                print("   Will fall back to creating drafts if agent is unavailable")
            else:
                print("   Processing will fail if agent is unavailable")
    
    # Test Outlook connection
    from outlook_client import OutlookClient
    outlook = OutlookClient()
    connection_test = outlook.test_connection()
    
    if connection_test["success"]:
        print(f"\n✅ Outlook connection successful")
    else:
        print(f"\n❌ Outlook connection failed: {connection_test['message']}")
        print("   Please check your Azure credentials in config.py")
        return
    
    # Start dashboard in a separate thread
    from dashboard import run_dashboard
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()
    
    # Start monitoring
    print("\n🚀 Starting monitoring...")
    start_monitoring_thread()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")


if __name__ == "__main__":
    main()
