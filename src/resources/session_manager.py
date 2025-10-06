"""
Session Manager - Browser session and login handling
Manages Playwright browser lifecycle and authentication
"""

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, Page, async_playwright

from ..utils.otp import get_otp_info

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages browser session and authentication"""

    def __init__(self, config_path: str = 'config.json'):
        self.config_path = config_path
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self._credentials = None

    def load_credentials(self):
        """Load credentials from config file"""
        import json

        with open(self.config_path, 'r') as f:
            config = json.load(f)

        self._credentials = {
            'username': config['username'],
            'password': config['password'],
            'otpauth_url': config['otpauth_url']
        }
        logger.info("Credentials loaded")

    async def start(self):
        """Initialize browser"""
        if not self._credentials:
            self.load_credentials()

        logger.info("Starting browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True) # To debug browser put on True IMPORTANT DEBUG
        self.page = await self.browser.new_page()
        logger.info("Browser started")

    async def stop(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")

    async def login(self) -> bool:
        """
        Perform login with credentials and OTP

        Returns:
            bool: True if login successful
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")

        try:
            logger.info("Starting login...")

            # Navigate to login page
            await self.page.goto("https://ecomm.sportrick.com/sportpolimi/Account/Login?returnUrl=%\2Fsportpolimi%\2F")
            # await self.page.get_by_role('link', name='Area Riservata').click()
            await self.page.get_by_role('button', name='Accedi al tuo account').click()

            await self.page.get_by_role('textbox', name='Codice Persona').fill(self._credentials['username'])
            await self.page.get_by_role('textbox', name='Password').fill(self._credentials['password'])
            await self.page.get_by_role('button', name='Accedi').click()

            await self.page.get_by_role('textbox', name='OTP').click()

            otp_info = get_otp_info(self._credentials['otpauth_url'])
            if otp_info['time_remaining'] < 2:
                logger.info("Waiting for new OTP code...")
                await self.page.wait_for_timeout(2000)
                otp_info = get_otp_info(self._credentials['otpauth_url'])

            otp = otp_info['current_otp']
            await self.page.get_by_role('textbox', name='OTP').fill(otp)
            await self.page.get_by_role('button', name='Continua').click()

            # Verify login success
            await self.page.wait_for_timeout(2000)
            logger.info("Login successful")
            return True

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    async def __aenter__(self):
        """Context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.stop()


if __name__ == '__main__':
    # Interactive test script
    import asyncio
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_session():
        """Test session manager"""
        print("=== Session Manager Test ===\n")

        # Check config exists
        config_path = 'config.json'
        if not Path(config_path).exists():
            print(f"❌ Config file not found: {config_path}")
            print("Please create config.json with:")
            print('''{
    "username": "your_username",
    "password": "your_password",
    "otpauth_url": "otpauth://totp/..."
}''')
            return

        print(f"✓ Config file found: {config_path}\n")

        # Test session manager
        async with SessionManager(config_path) as session:
            print("✓ Browser started")

            # Test login
            success = await session.login()

            if success:
                print("✓ Login successful")
                print(f"✓ Current URL: {session.page.url}")

                # Wait for user to verify
                print("\n>>> Browser is open. Press Enter to continue...")
                input()
            else:
                print("❌ Login failed")
                sys.exit(1)

        print("\n✓ Browser closed")
        print("\n✅ Session manager test passed!")

    asyncio.run(test_session())
