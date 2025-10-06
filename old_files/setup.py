#!/usr/bin/env python3
"""
Setup script - Initialize database and check configuration
"""

import json
import os
from database import Database


def check_config():
    """Check if configuration is valid"""
    if not os.path.exists('../config.json'):
        print("❌ config.json not found!")
        print("\nCreate config.json with the following structure:")
        print("""
{
  "username": "YOUR_POLIMISPORT_USERNAME",
  "password": "YOUR_POLIMISPORT_PASSWORD",
  "otpatu": "YOUR_OTP_URL",
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "allowed_user_id": YOUR_USER_ID
  }
}
        """)
        return False

    with open('config.json', 'r') as f:
        config = json.load(f)

    required_fields = ['username', 'password', 'otpatu']
    telegram_fields = ['bot_token', 'allowed_user_id']

    missing = []

    for field in required_fields:
        if field not in config or not config[field]:
            missing.append(field)

    if 'telegram' not in config:
        missing.extend([f'telegram.{f}' for f in telegram_fields])
    else:
        for field in telegram_fields:
            if field not in config['telegram'] or not config['telegram'][field]:
                missing.append(f'telegram.{field}')

    if missing:
        print(f"❌ Missing or empty fields in config.json: {', '.join(missing)}")
        return False

    print("✅ Configuration is valid")
    return True


def init_database():
    """Initialize database"""
    print("Initializing database...")

    if os.path.exists('polimisport.db'):
        response = input("Database already exists. Recreate? (y/N): ")
        if response.lower() != 'y':
            print("Skipping database initialization")
            return True
        os.remove('polimisport.db')

    try:
        db = Database()
        print("✅ Database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False


def main():
    print("=== Polimisport Bot Setup ===\n")

    # Check config
    if not check_config():
        print("\n❌ Setup failed: Invalid configuration")
        return 1

    # Initialize database
    if not init_database():
        print("\n❌ Setup failed: Database initialization error")
        return 1

    print("\n✅ Setup completed successfully!")
    print("\nNext steps:")
    print("1. Run 'python refresh_courses.py' to populate course database")
    print("2. Run 'python worker.py' in background to process bookings")
    print("3. Run 'python periodic_executor.py' in background for periodic bookings")
    print("4. Run 'python bot_db.py' to start the Telegram bot")
    print("\nOptional: Set up cron jobs for:")
    print("- refresh_courses.py (daily)")
    print("- sync_bookings.py (hourly)")

    return 0


if __name__ == '__main__':
    exit(main())
