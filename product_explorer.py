"""
Product Explorer - Automated Product Analysis Tool
Uses Browser-Use Cloud API to explore and document products
"""

import asyncio
import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from agentmail import AsyncAgentMail
import random
import string
import re
from openai import OpenAI

load_dotenv()


class ProductExplorer:
    """Explore and document products automatically using browser automation."""
    
    def __init__(
        self,
        agentmail_api_key: str,
        browser_use_api_key: str,
        openai_api_key: str,
        output_dir: str = "./outputs"
    ):
        self.agentmail_api_key = agentmail_api_key
        self.browser_use_api_key = browser_use_api_key
        self.openai_api_key = openai_api_key
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.api_base_url = "https://api.browser-use.com/api/v2"
        self.email_client = None
        self.inbox = None
        self.session_id = None
        self.task_id = None
        
    def _generate_password(self) -> str:
        """Generate a random secure password."""
        chars = string.ascii_letters + string.digits + "!@#$%"
        password = ''.join(random.choice(chars) for _ in range(16))
        return password
    
    async def create_temp_email(self) -> str:
        """Create a temporary email inbox."""
        if not self.email_client:
            self.email_client = AsyncAgentMail(api_key=self.agentmail_api_key)
        
        inbox = await self.email_client.inboxes.create()
        self.inbox = inbox
        return inbox.inbox_id
    
    async def get_verification_data(self, timeout: int = 90) -> Optional[Dict[str, str]]:
        """Wait for and retrieve verification code or link from email."""
        if not self.inbox:
            raise ValueError("No email inbox created")
        
        print(f"⏳ Waiting for verification email (timeout: {timeout}s)...")
        print(f"   📧 Monitoring inbox: {self.inbox.inbox_id}")
        
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout:
            check_count += 1
            elapsed = time.time() - start_time
            print(f"   🔍 Check #{check_count} (elapsed: {elapsed:.1f}s)")
            
            messages = await self.email_client.inboxes.messages.list(
                inbox_id=self.inbox.inbox_id
            )
            
            if messages.messages:
                latest_item = messages.messages[0]
                print(f"\n   ✉️  Email received!")
                print(f"      From: {getattr(latest_item, 'from_', 'unknown')}")
                print(f"      Subject: {getattr(latest_item, 'subject', 'No subject')}")
                
                try:
                    full_message = await self.email_client.inboxes.messages.get(
                        inbox_id=self.inbox.inbox_id,
                        message_id=latest_item.message_id
                    )
                    email_body = getattr(full_message, 'text', '') or getattr(full_message, 'html', '') or ""
                except Exception as e:
                    email_body = getattr(latest_item, 'preview', '') or ""
                
                # Use LLM to extract verification URL
                print(f"   🤖 Using GPT-4o to extract verification URL...")
                try:
                    openai_client = OpenAI(api_key=self.openai_api_key)
                    
                    response = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Extract the email verification URL from the email. Respond with ONLY the URL, nothing else. If there is no verification URL, respond with 'NONE'."},
                            {"role": "user", "content": f"Email subject: {getattr(latest_item, 'subject', '')}\n\nEmail body:\n{email_body}"}
                        ],
                        temperature=0,
                        max_tokens=16000
                    )
                    
                    extracted_url = response.choices[0].message.content.strip()
                    print(f"      ✅ LLM extracted: {extracted_url}")
                    
                    if extracted_url and extracted_url != 'NONE' and extracted_url.startswith('http'):
                        return {'type': 'link', 'value': extracted_url}
                    
                except Exception as e:
                    print(f"      ⚠️  LLM extraction failed: {e}")
                
                # Try verification codes
                code_patterns = [r'\b(\d{6})\b', r'\b(\d{4})\b']
                for pattern in code_patterns:
                    match = re.search(pattern, email_body, re.IGNORECASE)
                    if match:
                        code = match.group(1)
                        print(f"      ✅ CODE FOUND: {code}")
                        return {'type': 'code', 'value': code}
                
                return {'type': 'text', 'value': email_body[:1000]}
            
            await asyncio.sleep(3)
        
        print(f"\n   ❌ Timeout reached after {timeout}s")
        return None
    
    def stop_session(self, session_id: str):
        """Stop a session."""
        print(f"🛑 Stopping session {session_id}...")
        
        headers = {
            "X-Browser-Use-API-Key": self.browser_use_api_key,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.patch(
                f"{self.api_base_url}/sessions/{session_id}",
                headers=headers,
                json={"action": "stop"}
            )
            response.raise_for_status()
            print(f"✅ Session stopped")
        except Exception as e:
            print(f"⚠️  Failed to stop session: {e}")
    
    def create_session(self, start_url: Optional[str] = None, retries: int = 3) -> Dict[str, Any]:
        """Create a Browser-Use Cloud session with retry logic."""
        print("☁️  Creating Browser-Use Cloud session...")
        
        headers = {
            "X-Browser-Use-API-Key": self.browser_use_api_key,
            "Content-Type": "application/json"
        }
        
        payload = {}
        if start_url:
            payload["startUrl"] = start_url
        
        for attempt in range(retries):
            try:
                response = requests.post(
                    f"{self.api_base_url}/sessions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                session_data = response.json()
                
                self.session_id = session_data.get('id')
                live_url = session_data.get('liveUrl')
                
                print(f"✅ Session created: {self.session_id}")
                print(f"📺 Live view: {live_url}\n")
                
                return session_data
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait_time = (attempt + 1) * 15
                    print(f"⚠️  Rate limit hit. Waiting {wait_time}s before retry {attempt+1}/{retries}...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                print(f"❌ Failed to create session: {e}")
                raise
        
        raise Exception("Failed to create session after all retries")
    
    def create_task(self, task_description: str, session_id: Optional[str] = None, start_url: Optional[str] = None) -> Dict[str, Any]:
        """Create a task in the cloud."""
        print("📋 Creating cloud task...")
        
        headers = {
            "X-Browser-Use-API-Key": self.browser_use_api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "task": task_description,
            "llm": "browser-use-llm"
        }
        
        if session_id:
            payload["sessionId"] = session_id
        
        if start_url:
            payload["startUrl"] = start_url
        
        try:
            response = requests.post(
                f"{self.api_base_url}/tasks",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            task_data = response.json()
            
            self.task_id = task_data.get('id')
            print(f"✅ Task created: {self.task_id}\n")
            
            return task_data
        except Exception as e:
            print(f"❌ Failed to create task: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text}")
            raise
    
    async def wait_for_task_completion(self, check_interval: int = 5) -> Dict[str, Any]:
        """Poll for task completion, dynamically checking self.task_id."""
        print("⏳ Waiting for task to complete...")
        
        headers = {
            "X-Browser-Use-API-Key": self.browser_use_api_key
        }
        
        last_task_id = None
        
        while True:
            await asyncio.sleep(check_interval)
            
            # Check current task_id (may change if verification creates new session)
            current_task_id = self.task_id
            
            if current_task_id != last_task_id:
                if last_task_id:
                    print(f"   🔄 Task changed: {last_task_id} → {current_task_id}")
                last_task_id = current_task_id
            
            try:
                response = requests.get(
                    f"{self.api_base_url}/tasks/{current_task_id}",
                    headers=headers
                )
                response.raise_for_status()
                task_data = response.json()
                
                status = task_data.get('status')
                print(f"   Task status: {status}")
                
                if status in ['finished', 'stopped', 'failed']:
                    print(f"✅ Task {status}!")
                    return task_data
                    
            except Exception as e:
                print(f"❌ Error checking task status: {e}")
                await asyncio.sleep(5)
    
    def get_session_share_link(self, session_id: str) -> Optional[str]:
        """Get public share link for the session recording."""
        print("🔗 Getting public share link...")
        
        headers = {
            "X-Browser-Use-API-Key": self.browser_use_api_key
        }
        
        try:
            response = requests.post(
                f"{self.api_base_url}/sessions/{session_id}/public-share",
                headers=headers
            )
            response.raise_for_status()
            share_data = response.json()
            
            share_url = share_data.get('shareUrl')
            print(f"✅ Share URL: {share_url}\n")
            
            return share_url
        except Exception as e:
            print(f"❌ Failed to get share link: {e}")
            return None
    
    def _build_exploration_task(
        self,
        product_url: str,
        email: str,
        username: str,
        password: str
    ) -> str:
        """Build the comprehensive product exploration task."""
        
        from urllib.parse import urlparse
        site_name = urlparse(product_url).netloc
        
        task = f"""
You are a product analyst conducting a thorough exploration of a web application.

IMPORTANT: Stay on {site_name} throughout the entire exploration.

YOUR MISSION:
1. Sign up for an account and log in
2. Explore the product thoroughly to understand what it does
3. Document all major user actions/features available
4. Provide comprehensive analysis

================================================================================
PHASE 1: ACCOUNT CREATION & LOGIN
================================================================================

1. Find and click the "Sign Up" or "Create Account" or "Register" or "Get Started" button
2. Fill in the signup form with these credentials:
   - Email: {email}
   - Username (if asked): {username}
   - Password: {password}
   - Confirm Password (if asked): {password}
3. Handle any CAPTCHAs by clicking checkboxes or solving image challenges
4. Submit the signup form

5. Email Verification (if required):
   - After signup, check if email verification is needed
   - If you see "Check your email" or "Verify your email":
     * WAIT 20-30 seconds for verification email
     * The terminal will display a verification link when it arrives
     * When you see "VERIFICATION LINK RECEIVED", navigate to that link
     * This will automatically verify your account
   - If there's a code input field:
     * WAIT for the code to appear in terminal
     * Enter the code shown in terminal output
     * Submit the verification form

6. After verification, you should be logged into the dashboard/home page

================================================================================
PHASE 2: PRODUCT EXPLORATION & ANALYSIS
================================================================================

Now that you're logged in, conduct a THOROUGH exploration:

A. UNDERSTAND THE PRODUCT
   - What is the main purpose of this product?
   - What problem does it solve?
   - Who is the target user?
   - What category/industry is this product in?

B. EXPLORE THE INTERFACE
   - Navigate through ALL major sections (check navigation menu, sidebar, tabs)
   - Click into different pages and views
   - Look at settings, profile, documentation pages
   - Check for any onboarding tours or help sections
   - Don't rush - spend time understanding each section

C. IDENTIFY ALL HIGH-LEVEL ACTIONS
   For each major action/feature you discover, document:
   
   1. ACTION NAME: What is this action called?
   
   2. HOW TO START: Exact steps from the logged-in home page
      - Which menu/button to click
      - Which page to navigate to
      - Which tab or section to access
   
   3. WHAT IT DOES: What happens when you perform this action?
      - What inputs are required?
      - What is the output/result?
      - What changes in the product?
   
   4. PURPOSE: Why would a user perform this action?
      - What goal does it accomplish?
      - How does it fit into the product's overall workflow?
      - What use case does it serve?

D. EXPLORE THOROUGHLY
   - Create a test item/project/resource if the product allows
   - Try out key features hands-on
   - Look for "Create", "New", "Add" buttons
   - Check if there are templates or examples
   - Explore any API/integration sections
   - Look at billing/pricing pages if accessible

E. CHECK FOR HIDDEN FEATURES
   - Right-click menus
   - Keyboard shortcuts (look for help/shortcuts page)
   - Advanced settings
   - Admin or power-user features

================================================================================
PHASE 3: COMPREHENSIVE DOCUMENTATION
================================================================================

After your thorough exploration, provide a detailed summary in this EXACT format:

---START OF ANALYSIS---

## PRODUCT OVERVIEW

**Product Name:** [name of the product]
**URL:** {product_url}
**Category:** [e.g., project management, analytics, CRM, etc.]

**What This Product Is:**
[2-3 paragraph description explaining:
- What the product does
- What problem it solves
- Who it's for
- Key value proposition]

**Core Purpose:**
[1 paragraph summarizing the main reason this product exists]

---

## HIGH-LEVEL USER ACTIONS

[For EACH major action/feature you found, provide:]

### ACTION #1: [ACTION NAME]

**How to Start (from home page when logged in):**
1. [Step by step navigation]
2. [Be very specific about which buttons/menus to click]
3. [Include page names if relevant]

**What This Action Does:**
[Detailed explanation of what happens when you perform this action. Include:
- Required inputs
- What the system does
- What output/result you get]

**Purpose in the Product:**
[Explain why this action exists and how it serves the user's goals within the product's ecosystem]

---

### ACTION #2: [ACTION NAME]
... [repeat format] ...

### ACTION #3: [ACTION NAME]
... [repeat format] ...

[Continue for ALL major actions - aim for at least 5-10 actions]

---

## PRODUCT WORKFLOW

[Describe the typical user journey through the product:
- How do users typically start?
- What's the main workflow?
- How do the actions connect together?]

---

## ADDITIONAL OBSERVATIONS

[Any other important notes about:
- Unique features
- Limitations you noticed
- Target use cases
- Integration capabilities
- Pricing/plans if visible]

---END OF ANALYSIS---

IMPORTANT REMINDERS:
- Take your time - thorough exploration is more important than speed
- Navigate to EVERY section you can find
- Try to actually USE features, not just read about them
- Be specific in your action descriptions
- Stay on {site_name} - don't follow external links
"""
        
        return task
    
    async def _monitor_verification_email(self, temp_email: str, credentials: Dict[str, str], product_url: str):
        """Monitor for verification email and auto-navigate to link."""
        try:
            print(f"\n{'='*80}")
            print(f"📧 EMAIL MONITORING ACTIVE")
            print(f"Inbox: {temp_email}")
            print(f"{'='*80}\n")
            
            result = await self.get_verification_data(timeout=90)
            
            if result:
                v_type = result.get('type')
                value = result.get('value')
                
                if v_type == 'link':
                    print("\n" + "="*80)
                    print("🔗 VERIFICATION LINK RECEIVED!")
                    print("="*80)
                    print(f"\n   Link: {value}\n")
                    print("="*80 + "\n")
                    
                    # Stop old session and create new one with verification link
                    old_session_id = self.session_id
                    try:
                        self.stop_session(old_session_id)
                    except:
                        pass
                    
                    # Create new session starting at verification URL
                    verify_session = self.create_session(start_url=value)
                    self.session_id = verify_session.get('id')
                    
                    print(f"✅ New session created: {self.session_id}")
                    print(f"📺 Live: {verify_session.get('liveUrl')}\n")
                    
                    # Create task to complete verification and continue exploration
                    # Build FULL exploration task starting from verification
                    continuation_task = self._build_exploration_task(
                        product_url=product_url,
                        email=credentials['email'],
                        username=credentials['username'],
                        password=credentials['password']
                    )
                    
                    # Add note that verification link has been clicked
                    continuation_task = f"""
NOTE: The email verification link has already been opened. You may already be verified.

{continuation_task}

IMPORTANT: Since you're starting at the verification URL, you may skip directly to being logged in.
Check if you're already logged in. If not, proceed with login using the credentials above.
"""
                    
                    verify_task = self.create_task(continuation_task, session_id=self.session_id, start_url=value)
                    # CRITICAL: Update task_id so main loop waits for THIS task
                    self.task_id = verify_task.get('id')
                    
                elif v_type == 'code':
                    print("\n" + "="*80)
                    print("🔐 VERIFICATION CODE RECEIVED!")
                    print("="*80)
                    print(f"\n{value}\n")
                    print("="*80 + "\n")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Email monitoring error: {e}")
    
    async def explore_product(self, product_url: str) -> Dict[str, Any]:
        """Main method to explore a product and generate documentation."""
        
        print("\n" + "="*80)
        print("🔍 PRODUCT EXPLORER")
        print("="*80)
        print(f"📍 Target Product: {product_url}")
        print("="*80 + "\n")
        
        # Create temporary email for signup
        temp_email = await self.create_temp_email()
        print(f"📧 Temporary email: {temp_email}")
        
        # Generate credentials
        username = temp_email.split('@')[0]
        password = self._generate_password()
        
        credentials = {
            'email': temp_email,
            'username': username,
            'password': password
        }
        
        print(f"👤 Username: {username}")
        print(f"🔑 Password: {password}\n")
        
        # Build exploration task
        task_description = self._build_exploration_task(
            product_url=product_url,
            email=temp_email,
            username=username,
            password=password
        )
        
        # Create session
        session = self.create_session(start_url=product_url)
        
        print("\n" + "="*80)
        print("📺 WATCH LIVE")
        print("="*80)
        print(f"{session.get('liveUrl')}")
        print("="*80 + "\n")
        
        # Start email monitoring
        email_monitor_task = asyncio.create_task(
            self._monitor_verification_email(temp_email, credentials, product_url)
        )
        
        # Create and run task
        print("🚀 Starting product exploration...\n")
        start_time = datetime.now()
        
        task = self.create_task(task_description, session_id=self.session_id, start_url=product_url)
        
        # Wait for completion (monitors self.task_id dynamically)
        result = await self.wait_for_task_completion()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Cancel email monitoring
        if email_monitor_task and not email_monitor_task.done():
            email_monitor_task.cancel()
            try:
                await email_monitor_task
            except asyncio.CancelledError:
                pass
        
        print("\n" + "="*80)
        print("✅ EXPLORATION COMPLETED")
        print("="*80)
        print(f"⏱️  Duration: {duration:.1f} seconds")
        print(f"📊 Status: {result.get('status')}")
        print("="*80 + "\n")
        
        # Get share link
        share_url = self.get_session_share_link(self.session_id)
        
        # Extract analysis from task output
        task_output = result.get('output', '')
        
        # Prepare exploration data
        exploration_data = {
            'product_url': product_url,
            'timestamp': start_time.isoformat(),
            'duration_seconds': duration,
            'temp_email': temp_email,
            'username': username,
            'password': password,
            'session_id': self.session_id,
            'task_id': self.task_id,
            'share_url': share_url,
            'status': result.get('status'),
            'success': result.get('status') in ['finished', 'stopped'],  # Accept both finished and stopped
            'raw_analysis': task_output
        }
        
        # Parse and structure the analysis
        structured_analysis = self._parse_analysis(task_output)
        exploration_data['analysis'] = structured_analysis
        
        # Save results
        saved_files = self._save_exploration(exploration_data)
        exploration_data['saved_files'] = saved_files
        
        print(f"💾 Results saved to: {saved_files['json']}")
        print(f"📄 Readable report: {saved_files['txt']}")
        if share_url:
            print(f"📺 Recording: {share_url}")
        
        return exploration_data
    
    def _parse_analysis(self, raw_output: str) -> Dict[str, Any]:
        """Parse the structured analysis from task output."""
        analysis = {
            'product_overview': '',
            'product_purpose': '',
            'actions': [],
            'workflow': '',
            'observations': ''
        }
        
        # Try to extract structured sections
        # This is a basic parser - the LLM output should follow the format
        
        if '## PRODUCT OVERVIEW' in raw_output:
            overview_section = raw_output.split('## PRODUCT OVERVIEW')[1].split('##')[0].strip()
            analysis['product_overview'] = overview_section
        
        if '## HIGH-LEVEL USER ACTIONS' in raw_output:
            actions_section = raw_output.split('## HIGH-LEVEL USER ACTIONS')[1]
            if '## PRODUCT WORKFLOW' in actions_section:
                actions_section = actions_section.split('## PRODUCT WORKFLOW')[0]
            
            # Extract individual actions
            action_blocks = re.split(r'### ACTION #\d+:', actions_section)
            for block in action_blocks[1:]:  # Skip first empty split
                action_data = {
                    'name': '',
                    'how_to_start': '',
                    'what_it_does': '',
                    'purpose': ''
                }
                
                lines = block.strip().split('\n')
                if lines:
                    action_data['name'] = lines[0].strip()
                
                # Extract subsections
                full_text = block
                if '**How to Start' in full_text:
                    how_section = full_text.split('**How to Start')[1].split('**What This Action Does')[0]
                    action_data['how_to_start'] = how_section.strip()
                
                if '**What This Action Does' in full_text:
                    what_section = full_text.split('**What This Action Does')[1].split('**Purpose')[0]
                    action_data['what_it_does'] = what_section.strip()
                
                if '**Purpose' in full_text:
                    purpose_section = full_text.split('**Purpose')[1].split('###')[0]
                    action_data['purpose'] = purpose_section.strip()
                
                analysis['actions'].append(action_data)
        
        # Store raw output as fallback
        analysis['raw_output'] = raw_output
        
        return analysis
    
    def _save_exploration(self, exploration_data: Dict[str, Any]) -> Dict[str, str]:
        """Save exploration results to files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        from urllib.parse import urlparse
        domain = urlparse(exploration_data['product_url']).netloc.replace('.', '_')
        
        # Save JSON
        json_file = self.output_dir / f"exploration_{domain}_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(exploration_data, f, indent=2)
        
        # Save human-readable report
        txt_file = self.output_dir / f"exploration_{domain}_{timestamp}_REPORT.txt"
        with open(txt_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("PRODUCT EXPLORATION REPORT\n")
            f.write("="*80 + "\n\n")
            f.write(f"Product URL: {exploration_data['product_url']}\n")
            f.write(f"Explored on: {exploration_data['timestamp']}\n")
            f.write(f"Duration: {exploration_data['duration_seconds']:.1f} seconds\n")
            f.write(f"Status: {exploration_data['status']}\n\n")
            
            if exploration_data.get('share_url'):
                f.write(f"🎥 Recording: {exploration_data['share_url']}\n\n")
            
            f.write(f"Test Account:\n")
            f.write(f"  Email: {exploration_data['temp_email']}\n")
            f.write(f"  Password: {exploration_data['password']}\n\n")
            
            f.write("="*80 + "\n")
            f.write("ANALYSIS\n")
            f.write("="*80 + "\n\n")
            
            # Write the analysis
            analysis = exploration_data.get('analysis', {})
            if analysis.get('raw_output'):
                f.write(analysis['raw_output'])
            else:
                f.write(exploration_data.get('raw_analysis', 'No analysis available'))
        
        return {
            'json': str(json_file),
            'txt': str(txt_file)
        }


async def main():
    """Test the product explorer."""
    
    agentmail_key = os.getenv('AGENTMAIL_API_KEY')
    browser_use_key = os.getenv('BROWSER_USE_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    if not agentmail_key or not browser_use_key or not openai_key:
        print("❌ Error: API keys not found in .env")
        print("Required keys: AGENTMAIL_API_KEY, BROWSER_USE_API_KEY, OPENAI_API_KEY")
        return
    
    explorer = ProductExplorer(
        agentmail_api_key=agentmail_key,
        browser_use_api_key=browser_use_key,
        openai_api_key=openai_key,
        output_dir="./outputs"
    )
    
    # Example: Explore a product
    result = await explorer.explore_product(
        product_url="https://cloud.browser-use.com/"
    )
    
    print("\n" + "="*80)
    print("📊 EXPLORATION RESULTS")
    print("="*80)
    print(f"✅ Success: {result['success']}")
    print(f"⏱️  Duration: {result['duration_seconds']:.1f}s")
    print(f"📄 Report: {result['saved_files']['txt']}")
    print(f"📊 Data: {result['saved_files']['json']}")
    if result.get('share_url'):
        print(f"📺 Recording: {result['share_url']}")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())

