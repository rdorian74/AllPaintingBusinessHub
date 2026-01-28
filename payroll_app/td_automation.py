"""
TD E-Transfer Automation Module
================================
Uses Selenium to automate filling e-Transfer forms in TD EasyWeb.
User must click Send button manually for each payment.

Author: Built for All Painting Ltd
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json


class TDAutomation:
    """Automates TD EasyWeb e-Transfer form filling."""
    
    def __init__(self, headless=False):
        """Initialize the browser."""
        self.driver = None
        self.headless = headless
        self.logged_in = False
        self.current_payment_index = 0
        self.payments = []
        self.results = []
        
    def start_browser(self):
        """Start Chrome browser."""
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--start-maximized')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Suppress logging
        options.add_argument('--log-level=3')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return True
    
    def open_td_login(self):
        """Navigate to TD EasyWeb login page."""
        if not self.driver:
            self.start_browser()
        
        self.driver.get('https://easyweb.td.com')
        return True
    
    def wait_for_login(self, timeout=300):
        """
        Wait for user to log in manually.
        Returns True when logged in, False if timeout.
        """
        print("Waiting for user to log in...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check for elements that appear after login
                # TD shows account summary or dashboard after login
                if self.is_logged_in():
                    self.logged_in = True
                    print("Login detected!")
                    return True
            except:
                pass
            time.sleep(2)
        
        return False
    
    def is_logged_in(self):
        """Check if user is logged into TD."""
        try:
            # Look for common post-login elements
            indicators = [
                "//a[contains(text(), 'Accounts')]",
                "//span[contains(text(), 'Accounts')]",
                "//a[contains(text(), 'Transfer')]",
                "//div[contains(@class, 'account')]",
                "//*[contains(text(), 'BUSINESS PLAN')]",
                "//*[contains(text(), 'Send Money')]",
            ]
            
            for xpath in indicators:
                try:
                    element = self.driver.find_element(By.XPATH, xpath)
                    if element.is_displayed():
                        return True
                except:
                    continue
            
            # Also check URL - after login URL changes
            current_url = self.driver.current_url.lower()
            if 'easyweb' in current_url and 'login' not in current_url:
                # Additional check - login page has specific elements
                try:
                    login_button = self.driver.find_element(By.ID, 'login')
                    return False  # Still on login page
                except:
                    return True  # Login button not found, probably logged in
                    
            return False
        except:
            return False
    
    def navigate_to_etransfer(self):
        """Navigate to the e-Transfer Send Money page."""
        try:
            wait = WebDriverWait(self.driver, 10)
            
            # Try different navigation paths
            nav_attempts = [
                # Try clicking Transfer menu
                ("//a[contains(text(), 'Transfer')]", "//a[contains(text(), 'Send Interac')]"),
                ("//span[contains(text(), 'Transfer')]", "//a[contains(text(), 'e-Transfer')]"),
                # Direct link attempts
                ("//a[contains(text(), 'Interac e-Transfer')]", None),
                ("//a[contains(text(), 'Send Money')]", None),
            ]
            
            for first_click, second_click in nav_attempts:
                try:
                    element = wait.until(EC.element_to_be_clickable((By.XPATH, first_click)))
                    element.click()
                    time.sleep(1)
                    
                    if second_click:
                        element2 = wait.until(EC.element_to_be_clickable((By.XPATH, second_click)))
                        element2.click()
                        time.sleep(1)
                    
                    return True
                except:
                    continue
            
            # If clicking didn't work, try direct URL
            self.driver.get('https://easyweb.td.com/waw/idp/login.htm?execution=e1s1')
            time.sleep(2)
            
            return True
            
        except Exception as e:
            print(f"Error navigating to e-Transfer: {e}")
            return False
    
    def fill_etransfer_form(self, recipient_email, amount, recipient_name, message="", security_question="", security_answer=""):
        """
        Fill in the e-Transfer form fields.
        Does NOT click Send - user must do that.
        
        Returns dict with status and any errors.
        """
        result = {
            'success': False,
            'recipient': recipient_name,
            'email': recipient_email,
            'amount': amount,
            'error': None
        }
        
        try:
            wait = WebDriverWait(self.driver, 10)
            
            # Common field IDs/names TD might use (these may need adjustment)
            # TD's actual field names change, so we try multiple selectors
            
            # Fill recipient email
            email_selectors = [
                "//input[@id='recipientEmail']",
                "//input[@name='recipientEmail']",
                "//input[contains(@id, 'email')]",
                "//input[contains(@placeholder, 'email')]",
                "//input[@type='email']",
            ]
            
            email_filled = False
            for selector in email_selectors:
                try:
                    email_field = self.driver.find_element(By.XPATH, selector)
                    email_field.clear()
                    email_field.send_keys(recipient_email)
                    email_filled = True
                    break
                except:
                    continue
            
            if not email_filled:
                result['error'] = "Could not find email field"
                return result
            
            time.sleep(0.5)
            
            # Fill amount
            amount_selectors = [
                "//input[@id='amount']",
                "//input[@name='amount']",
                "//input[contains(@id, 'amount')]",
                "//input[contains(@placeholder, 'Amount')]",
                "//input[@type='number']",
            ]
            
            amount_filled = False
            for selector in amount_selectors:
                try:
                    amount_field = self.driver.find_element(By.XPATH, selector)
                    amount_field.clear()
                    amount_field.send_keys(str(amount))
                    amount_filled = True
                    break
                except:
                    continue
            
            if not amount_filled:
                result['error'] = "Could not find amount field"
                return result
            
            time.sleep(0.5)
            
            # Fill message if provided
            if message:
                message_selectors = [
                    "//textarea[@id='message']",
                    "//textarea[@name='message']",
                    "//input[contains(@id, 'message')]",
                    "//textarea[contains(@placeholder, 'message')]",
                ]
                
                for selector in message_selectors:
                    try:
                        msg_field = self.driver.find_element(By.XPATH, selector)
                        msg_field.clear()
                        msg_field.send_keys(message)
                        break
                    except:
                        continue
            
            # Fill security question if not auto-deposit
            if security_question and security_answer:
                sq_selectors = [
                    "//input[@id='securityQuestion']",
                    "//input[contains(@id, 'security')]",
                    "//input[contains(@placeholder, 'question')]",
                ]
                
                for selector in sq_selectors:
                    try:
                        sq_field = self.driver.find_element(By.XPATH, selector)
                        sq_field.clear()
                        sq_field.send_keys(security_question)
                        break
                    except:
                        continue
                
                sa_selectors = [
                    "//input[@id='securityAnswer']",
                    "//input[contains(@id, 'answer')]",
                    "//input[contains(@placeholder, 'answer')]",
                ]
                
                for selector in sa_selectors:
                    try:
                        sa_field = self.driver.find_element(By.XPATH, selector)
                        sa_field.clear()
                        sa_field.send_keys(security_answer)
                        break
                    except:
                        continue
            
            result['success'] = True
            result['message'] = "Form filled - please review and click SEND"
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            return result
    
    def wait_for_send_completion(self, timeout=120):
        """
        Wait for user to click Send and for confirmation to appear.
        Returns True if send was successful.
        """
        print("Waiting for user to click Send...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Look for success/confirmation indicators
                success_indicators = [
                    "//*[contains(text(), 'successfully')]",
                    "//*[contains(text(), 'has been sent')]",
                    "//*[contains(text(), 'Confirmation')]",
                    "//*[contains(text(), 'Receipt')]",
                    "//*[contains(@class, 'success')]",
                ]
                
                for xpath in success_indicators:
                    try:
                        element = self.driver.find_element(By.XPATH, xpath)
                        if element.is_displayed():
                            return True
                    except:
                        continue
                        
            except:
                pass
            
            time.sleep(1)
        
        return False
    
    def click_send_another(self):
        """Click 'Send Another' or similar button to start next transfer."""
        try:
            buttons = [
                "//a[contains(text(), 'Send Another')]",
                "//button[contains(text(), 'Send Another')]",
                "//a[contains(text(), 'New Transfer')]",
                "//button[contains(text(), 'New')]",
                "//a[contains(text(), 'Send Money')]",
            ]
            
            for xpath in buttons:
                try:
                    btn = self.driver.find_element(By.XPATH, xpath)
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(2)
                        return True
                except:
                    continue
            
            # If no button found, navigate back to send page
            self.navigate_to_etransfer()
            return True
            
        except Exception as e:
            print(f"Error clicking send another: {e}")
            return False
    
    def process_payments(self, payments, default_security_question="", default_security_answer="", message_template=""):
        """
        Process a list of payments.
        
        payments: list of dicts with keys:
            - employee_name
            - etransfer_email
            - net_pay (amount)
            - security_question (optional)
            - security_answer (optional)
            - auto_deposit (bool)
        
        Returns list of results for each payment.
        """
        self.payments = payments
        self.results = []
        
        for i, payment in enumerate(payments):
            print(f"\n--- Payment {i+1} of {len(payments)} ---")
            print(f"Employee: {payment['employee_name']}")
            print(f"Amount: ${payment['net_pay']:.2f}")
            print(f"Email: {payment['etransfer_email']}")
            
            # Determine security Q&A
            sq = payment.get('security_question') or default_security_question
            sa = payment.get('security_answer') or default_security_answer
            
            # Skip security if auto-deposit
            if payment.get('auto_deposit'):
                sq = ""
                sa = ""
            
            # Build message
            message = message_template.replace('{employee}', payment['employee_name'])
            
            # Fill the form
            result = self.fill_etransfer_form(
                recipient_email=payment['etransfer_email'],
                amount=payment['net_pay'],
                recipient_name=payment['employee_name'],
                message=message,
                security_question=sq,
                security_answer=sa
            )
            
            if result['success']:
                print("✓ Form filled! Please review and click SEND in the browser.")
                
                # Wait for user to send
                if self.wait_for_send_completion():
                    result['sent'] = True
                    print("✓ Payment sent successfully!")
                    
                    # Click to send another if more payments
                    if i < len(payments) - 1:
                        self.click_send_another()
                else:
                    result['sent'] = False
                    print("⚠ Timed out waiting for send confirmation")
            else:
                print(f"✗ Error: {result['error']}")
                result['sent'] = False
            
            self.results.append(result)
        
        return self.results
    
    def close(self):
        """Close the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None


# Standalone test
if __name__ == '__main__':
    print("TD Automation Module")
    print("=" * 40)
    
    auto = TDAutomation()
    auto.start_browser()
    auto.open_td_login()
    
    print("\nPlease log into TD EasyWeb...")
    print("Press Enter when logged in...")
    input()
    
    if auto.is_logged_in():
        print("✓ Login confirmed!")
    else:
        print("Could not confirm login")
    
    auto.close()
