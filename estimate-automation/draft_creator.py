"""
Draft Creator - Creates professional email drafts for estimates
"""
import re
from outlook_client import OutlookClient
import config


class DraftCreator:
    """Creates professional email drafts for estimates"""
    
    def __init__(self):
        self.outlook = OutlookClient()
        self.drafts_folder_id = None
    
    def get_drafts_folder_id(self):
        """Get or create the drafts folder"""
        if self.drafts_folder_id is None:
            self.drafts_folder_id = self.outlook.get_or_create_folder(
                config.DRAFTS_FOLDER_NAME
            )
        return self.drafts_folder_id
    
    def extract_client_email(self, extracted_data):
        """Extract client email from the estimate data"""
        client_info = extracted_data.get("client_info", {})
        email = client_info.get("email", "")
        
        if email and "@" in email:
            # Handle multiple emails separated by /
            if "/" in email:
                email = email.split("/")[0].strip()
            return email
        
        return None
    
    def extract_contact_name(self, extracted_data):
        """Extract contact person's first name for greeting"""
        client_info = extracted_data.get("client_info", {})
        contact = client_info.get("contact_person", "")
        
        if contact:
            # Handle multiple contacts separated by /
            if "/" in contact:
                contact = contact.split("/")[0].strip()
            
            # Get first name
            first_name = contact.split()[0] if contact else ""
            return first_name
        
        return None
    
    def extract_project_info(self, extracted_data):
        """Extract project name and address"""
        project_info = extracted_data.get("project_info", {})
        
        project_name = project_info.get("name", "")
        project_address = project_info.get("address", "")
        project_city = project_info.get("city_province_postal", "")
        
        # Combine address parts
        full_address = project_address
        if project_city:
            full_address = f"{project_address} in {project_city}" if project_address else project_city
        
        return {
            "name": project_name,
            "address": project_address,
            "full_address": full_address
        }
    
    def generate_email_body(self, estimate_code, project_info, contact_name, pdf_filename):
        """
        Generate a professional, convincing email body
        
        Args:
            estimate_code: The estimate number
            project_info: Dictionary with project name and address
            contact_name: First name of the contact person
            pdf_filename: Name of the PDF file
        
        Returns:
            HTML email body
        """
        # Greeting
        if contact_name:
            greeting = f"Hi {contact_name},"
        else:
            greeting = "Hello,"
        
        # Project description
        project_name = project_info.get("name", "painting project")
        full_address = project_info.get("full_address", "")
        
        # Build the project description
        if project_name and full_address:
            project_desc = f"the {project_name} project located at {full_address}"
        elif project_name:
            project_desc = f"the {project_name} project"
        elif full_address:
            project_desc = f"the project located at {full_address}"
        else:
            project_desc = "your project"
        
        # Email body - professional and convincing
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
        return body_html
    
    def create_estimate_draft(self, pdf_path, pdf_filename, extracted_data, estimate_code):
        """
        Create a draft email for an estimate
        
        Args:
            pdf_path: Full path to the PDF file
            pdf_filename: Name of the PDF file (for subject)
            extracted_data: Data extracted from the estimate
            estimate_code: The estimate code
        
        Returns:
            Dictionary with result info
        """
        print(f"📧 Creating email draft for estimate {estimate_code}...")
        
        # Extract information
        client_email = self.extract_client_email(extracted_data)
        contact_name = self.extract_contact_name(extracted_data)
        project_info = self.extract_project_info(extracted_data)
        
        # Check if we have a client email
        if not client_email:
            return {
                "success": False,
                "error": "Could not find client email in estimate data",
                "estimate_code": estimate_code
            }
        
        # Generate subject from PDF filename
        # Remove "Estimate - " prefix if present and ".pdf" extension
        subject = pdf_filename
        if subject.startswith("Estimate - "):
            subject = "Estimate - " + subject[11:]  # Keep the prefix but clean
        if subject.lower().endswith(".pdf"):
            subject = subject[:-4]
        
        # Generate email body
        body_html = self.generate_email_body(
            estimate_code=estimate_code,
            project_info=project_info,
            contact_name=contact_name,
            pdf_filename=pdf_filename
        )
        
        try:
            # Get or create the drafts folder
            folder_id = self.get_drafts_folder_id()
            
            # Create draft with attachment
            draft = self.outlook.create_draft_with_attachment(
                to_email=client_email,
                subject=subject,
                body_html=body_html,
                attachment_path=pdf_path,
                folder_id=folder_id
            )
            
            print(f"   ✅ Draft created successfully")
            print(f"   📬 To: {client_email}")
            print(f"   📎 Subject: {subject}")
            
            return {
                "success": True,
                "draft_id": draft.get("id"),
                "to_email": client_email,
                "subject": subject,
                "estimate_code": estimate_code
            }
        
        except Exception as e:
            print(f"   ❌ Error creating draft: {e}")
            return {
                "success": False,
                "error": str(e),
                "estimate_code": estimate_code
            }


# Test the draft creator if run directly
if __name__ == "__main__":
    print("Testing Draft Creator...")
    
    creator = DraftCreator()
    
    # Test with sample data
    sample_data = {
        "client_info": {
            "company_name": "Test Construction",
            "contact_person": "John Smith",
            "email": "john@testconstruction.com"
        },
        "project_info": {
            "name": "Office Building Renovation",
            "address": "123 Main St",
            "city_province_postal": "Vancouver, BC"
        },
        "estimate_number": "25C-999"
    }
    
    # Test extraction
    print(f"\nClient email: {creator.extract_client_email(sample_data)}")
    print(f"Contact name: {creator.extract_contact_name(sample_data)}")
    print(f"Project info: {creator.extract_project_info(sample_data)}")
    
    # Test email body generation
    body = creator.generate_email_body(
        estimate_code="25C-999",
        project_info=creator.extract_project_info(sample_data),
        contact_name=creator.extract_contact_name(sample_data),
        pdf_filename="Estimate - 25C-999 Office Building.pdf"
    )
    print(f"\nGenerated email body preview:")
    print(body[:500] + "...")
