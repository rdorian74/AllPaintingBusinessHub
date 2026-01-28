"""
Estimate Processor - Finds Word documents and generates PDFs
"""
import os
import re
import requests
from pathlib import Path
import config


class EstimateProcessor:
    """Processes estimates: finds Word files and generates PDFs"""
    
    def __init__(self):
        self.estimate_folders = config.ESTIMATE_FOLDERS
        self.api_url = config.ESTIMATE_GENERATOR_URL
    
    def find_word_document(self, estimate_code):
        """
        Find the Word document for an estimate
        
        Args:
            estimate_code: Estimate code (e.g., 25C-318) or tuple of variants
        
        Returns:
            Full path to the Word document, or None if not found
        """
        # Handle both string and tuple input
        if isinstance(estimate_code, tuple):
            code_variants = estimate_code
        else:
            # Create variants (with and without dash)
            code_clean = estimate_code.replace("-", "").upper()
            code_with_dash = estimate_code.upper()
            code_variants = (code_with_dash, code_clean)
        
        print(f"🔍 Searching for Word document with code variants: {code_variants}")
        
        found_files = []
        
        for folder in self.estimate_folders:
            if not os.path.exists(folder):
                print(f"   ⚠️ Folder does not exist: {folder}")
                continue
            
            # Walk through folder and subfolders
            for root, dirs, files in os.walk(folder):
                for filename in files:
                    # Check if it's a Word document
                    if not filename.lower().endswith(('.doc', '.docx')):
                        continue
                    
                    # Check if filename contains the estimate code
                    filename_upper = filename.upper()
                    
                    for variant in code_variants:
                        if variant in filename_upper:
                            # Check if it contains "(working)"
                            if "(working)" in filename.lower():
                                full_path = os.path.join(root, filename)
                                found_files.append(full_path)
                                print(f"   ✅ Found: {full_path}")
                            break
        
        if not found_files:
            print(f"   ❌ No Word document found with (working) in name")
            return None
        
        if len(found_files) > 1:
            print(f"   ⚠️ Multiple files found, using first one")
        
        return found_files[0]
    
    def check_api_health(self):
        """Check if the estimate generator API is running"""
        try:
            response = requests.get(config.ESTIMATE_GENERATOR_HEALTH_URL, timeout=5)
            if response.status_code == 200:
                return True
        except:
            pass
        return False
    
    def generate_pdf(self, word_file_path):
        """
        Generate PDF from Word document using the estimate generator API
        
        Args:
            word_file_path: Full path to the Word document
        
        Returns:
            Dictionary with result info including pdf_path and extracted_data
        """
        print(f"📄 Generating PDF for: {word_file_path}")
        
        # Check if API is running
        if not self.check_api_health():
            return {
                "success": False,
                "error": "Estimate Generator API is not running. Please start it first."
            }
        
        # Call the API
        try:
            response = requests.post(
                self.api_url,
                json={"word_file_path": word_file_path},
                timeout=300  # 5 minute timeout for processing
            )
            
            result = response.json()
            
            if result.get("success"):
                print(f"   ✅ PDF generated: {result.get('pdf_path')}")
            else:
                print(f"   ❌ Error: {result.get('error')}")
            
            return result
        
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "API request timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def process_estimate(self, estimate_info):
        """
        Full process: find Word document and generate PDF
        
        Args:
            estimate_info: Dictionary with estimate code and variants
        
        Returns:
            Dictionary with processing result
        """
        code = estimate_info.get("code")
        code_variants = estimate_info.get("code_variants", (code, code.replace("-", "")))
        
        print(f"\n{'='*60}")
        print(f"PROCESSING ESTIMATE: {code}")
        print(f"{'='*60}")
        
        # Step 1: Find the Word document
        word_path = self.find_word_document(code_variants)
        
        if not word_path:
            return {
                "success": False,
                "error": f"Word document not found for code: {code}",
                "estimate_code": code
            }
        
        # Step 2: Generate the PDF
        result = self.generate_pdf(word_path)
        
        # Add estimate info to result
        result["estimate_code"] = code
        result["word_file_original"] = word_path
        
        return result


# Test the processor if run directly
if __name__ == "__main__":
    print("Testing Estimate Processor...")
    
    processor = EstimateProcessor()
    
    # Check API health
    print(f"\nAPI Health: {processor.check_api_health()}")
    
    # Test finding a document
    test_code = "25C-325"
    print(f"\nSearching for {test_code}...")
    
    word_path = processor.find_word_document(test_code)
    
    if word_path:
        print(f"\nFound: {word_path}")
        
        # Optionally test PDF generation
        # result = processor.generate_pdf(word_path)
        # print(f"Result: {result}")
    else:
        print("Not found")
