#!/usr/bin/env python3
"""
Test Full Flow
Interactive script to test complete workflow: login → scrape → store
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import Database
from src.resources import SessionManager
from src.handlers import CourseHandler, BookingHandler

async def main():
    print("=== Full Flow Test ===\n")

    # Check config
    config_path = 'config.json'
    if not Path(config_path).exists():
        print(f"❌ Config file not found: {config_path}")
        return

    print(f"✓ Config file found\n")

    # Initialize database
    db = Database('test_polimisport.db')
    print("✓ Database initialized (test_polimisport.db)\n")

    # Initialize session
    print(">>> Starting browser and logging in...")
    async with SessionManager(config_path) as session:
        print("✓ Browser started")

        if not await session.login():
            print("❌ Login failed")
            return

        print("✓ Login successful\n")

        # Initialize handlers
        course_handler = CourseHandler(db, session)
        booking_handler = BookingHandler(db, session)

        # Test 1: Refresh courses
        print(">>> Test 1: Refreshing courses (1 page)...")
        course_count = await course_handler.refresh_courses(pages_to_scrape=1)
        print(f"✓ Stored {course_count} courses\n")

        # Test 2: Refresh fit center
        print(">>> Test 2: Refreshing fit center (1 page)...")
        fit_count = await course_handler.refresh_fit_center(pages_to_scrape=1)
        print(f"✓ Stored {fit_count} fit center slots\n")

        # Test 3: Show sample data
        print(">>> Test 3: Retrieving sample courses...")
        for day in ["Lunedì", "Martedì"]:
            courses = course_handler.get_courses_by_day(day)
            if courses:
                print(f"\n{day}:")
                for c in courses[:3]:  # Show first 3
                    print(f"  - {course_handler.format_course_text(c)}")

        # Test 4: Sync bookings
        print("\n>>> Test 4: Syncing bookings...")
        user_id = 123456  # Test user ID
        booking_count = await booking_handler.sync_bookings(user_id)
        print(f"✓ Synced {booking_count} bookings\n")

        # Show bookings
        bookings = booking_handler.get_user_bookings(user_id)
        if bookings:
            print("Current bookings:")
            for b in bookings:
                print(f"  - {booking_handler.format_booking_text(b)}")
        else:
            print("No bookings found")

        # Keep browser open
        print("\n" + "=" * 50)
        print("Full flow completed successfully!")
        print("Browser window is open for inspection.")
        print("=" * 50)
        print("\n>>> Press Enter to close...")
        input()

    print("\n✓ Browser closed")
    print("\n✅ All tests passed!")
    print(f"\nDatabase saved to: test_polimisport.db")

if __name__ == '__main__':
    asyncio.run(main())
