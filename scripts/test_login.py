#!/usr/bin/env python3
"""
Test Login and Session
Interactive script to test browser session and login
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.resources import SessionManager

async def main():
    print("=== Session Manager & Login Test ===\n")

    # Check config
    config_path = 'config.json'
    if not Path(config_path).exists():
        print(f"❌ Config file not found: {config_path}")
        print("\nPlease create config.json with:")
        print('''{
    "username": "your_username",
    "password": "your_password",
    "otpauth_url": "otpauth://totp/...",
    "telegram_bot_token": "your_bot_token",
    "telegram_user_id": 123456,
    "db_path": "polimisport.db"
}''')
        return

    print(f"✓ Config file found: {config_path}\n")

    # Initialize session
    print(">>> Starting browser session...")
    async with SessionManager(config_path) as session:
        print("✓ Browser started (headless=False)\n")

        # Test login
        print(">>> Attempting login...")
        success = await session.login()

        if success:
            print("✓ Login successful!")
            print(f"✓ Current URL: {session.page.url}\n")

            # Test navigation
            print(">>> Testing navigation to bookings page...")
            await session.page.goto('https://sport.polimi.it/bookings', wait_until='domcontentloaded')
            await session.page.wait_for_timeout(2000)
            print(f"✓ Navigated to: {session.page.url}\n")

            # Keep browser open for inspection
            print("=" * 50)
            print("Browser is open for inspection.")
            print("Check the browser window to verify login success.")
            print("=" * 50)
            print("\n>>> Press Enter to close browser...")
            input()

        else:
            print("❌ Login failed!")
            print("Check your credentials in config.json\n")
            return

    print("✓ Browser closed\n")
    print("✅ Session manager test completed!")

if __name__ == '__main__':
    asyncio.run(main())
