"""
Course Handler - Business logic for course management
Coordinates scraping, database storage, and course retrieval
"""

import logging
from typing import Dict, List

from ..resources import SessionManager, WebScraper
from ..utils import Database

logger = logging.getLogger(__name__)


class CourseHandler:
    """Handles course-related operations"""

    def __init__(self, db: Database, session: SessionManager):
        self.db = db
        self.session = session

    async def refresh_courses(self, pages_to_scrape: int = 5) -> tuple[int, List[Dict]]:
        """
        Scrape and refresh course database

        Args:
            pages_to_scrape: Number of date pages to scrape

        Returns:
            Tuple of (number of courses stored, list of bookings)
        """
        logger.info("Refreshing courses...")

        # Navigate to courses and scrape bookings
        bookings = await WebScraper.navigate_to_courses(self.session.page)

        # Scrape weekly schedule
        weekly_data = await WebScraper.scrape_schedule(
            self.session.page,
            pages_to_scrape=pages_to_scrape
        )

        # Store in database with deduplication
        stored_count = 0
        seen_courses = set()

        for day_name, events in weekly_data.items():
            for event in events:
                # Create unique key for deduplication
                unique_key = (
                    day_name,
                    event.get('time_start'),
                    event.get('skill'),
                    event.get('instructor'),
                    event.get('location_path')
                )

                if unique_key not in seen_courses:
                    seen_courses.add(unique_key)

                    course = {
                        'name': event.get('skill') or event.get('activity_full', 'Unknown'),
                        'location': event.get('location_path', 'Unknown'),
                        'day_of_week': day_name,
                        'time_start': event.get('time_start'),
                        'time_end': event.get('time_end'),
                        'course_type': event.get('course_type'),
                        'instructor': event.get('instructor'),
                        'is_fit_center': False
                    }

                    self.db.add_course(course)
                    stored_count += 1

        logger.info(f"Stored {stored_count} unique courses")
        return stored_count, bookings

    async def refresh_fit_center(self, pages_to_scrape: int = 5) -> int:
        """
        Scrape and refresh fit center database

        Args:
            pages_to_scrape: Number of date pages to scrape

        Returns:
            Number of fit center slots stored
        """
        logger.info("Refreshing fit center...")

        # Navigate to fit center
        await WebScraper.navigate_to_fit_center(self.session.page)

        # Scrape weekly schedule
        weekly_data = await WebScraper.scrape_schedule(
            self.session.page,
            pages_to_scrape=pages_to_scrape
        )

        # Store in database with deduplication
        stored_count = 0
        seen_slots = set()

        for day_name, events in weekly_data.items():
            for event in events:
                # Create unique key for deduplication
                unique_key = (
                    day_name,
                    event.get('time_start'),
                    event.get('location_path')
                )

                if unique_key not in seen_slots:
                    seen_slots.add(unique_key)

                    slot = {
                        'name': 'Fit Center',
                        'location': event.get('location_path', 'Unknown'),
                        'day_of_week': day_name,
                        'time_start': event.get('time_start'),
                        'time_end': event.get('time_end'),
                        'course_type': None,
                        'instructor': None,
                        'is_fit_center': True
                    }

                    self.db.add_course(slot)
                    stored_count += 1

        logger.info(f"Stored {stored_count} unique fit center slots")
        return stored_count

    def get_courses_by_day(self, day_name: str, include_fit_center: bool = False) -> List[Dict]:
        """
        Get courses for a specific day

        Args:
            day_name: Italian day name (e.g., "Lunedì")
            include_fit_center: Whether to include fit center slots

        Returns:
            List of course dictionaries
        """
        all_courses = self.db.get_all_courses(include_fit_center=include_fit_center)
        return [c for c in all_courses if c['day_of_week'] == day_name]

    def get_fit_center_by_day(self, day_name: str) -> List[Dict]:
        """
        Get fit center slots for a specific day

        Args:
            day_name: Italian day name (e.g., "Lunedì")

        Returns:
            List of fit center slot dictionaries
        """
        all_slots = self.db.get_fit_center_slots()
        return [s for s in all_slots if s['day_of_week'] == day_name]

    def format_course_text(self, course: Dict) -> str:
        """
        Format course for display

        Args:
            course: Course dictionary

        Returns:
            Formatted string
        """
        if course.get('is_fit_center'):
            return f"{course['time_start']}-{course['time_end']} | {course['location']}"
        else:
            parts = [
                f"{course['time_start']}-{course['time_end']}",
                course['name']
            ]
            if course.get('instructor'):
                parts.append(course['instructor'])
            if course.get('location'):
                parts.append(course['location'])

            return " | ".join(parts)


if __name__ == '__main__':
    # Interactive test script
    import asyncio
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_course_handler():
        """Test course handler"""
        print("=== Course Handler Test ===\n")

        # Check config
        config_path = 'config.json'
        if not Path(config_path).exists():
            print(f"❌ Config file not found: {config_path}")
            return

        # Initialize components
        db = Database(':memory:')  # Use in-memory for testing
        print("✓ Database initialized\n")

        async with SessionManager(config_path) as session:
            print("✓ Browser started")

            # Login
            if not await session.login():
                print("❌ Login failed")
                return
            print("✓ Login successful\n")

            # Create handler
            handler = CourseHandler(db, session)

            # Test course refresh
            print(">>> Refreshing courses (1 page)...")
            course_count = await handler.refresh_courses(pages_to_scrape=1)
            print(f"✓ Stored {course_count} courses\n")

            # Test fit center refresh
            print(">>> Refreshing fit center (1 page)...")
            fit_count = await handler.refresh_fit_center(pages_to_scrape=1)
            print(f"✓ Stored {fit_count} fit center slots\n")

            # Show sample courses
            print(">>> Sample courses by day:")
            for day in ["Lunedì", "Martedì", "Mercoledì"]:
                courses = handler.get_courses_by_day(day)
                if courses:
                    print(f"\n{day}:")
                    for c in courses[:3]:  # Show first 3
                        print(f"  - {handler.format_course_text(c)}")

        print("\n\n✅ Course handler test passed!")

    asyncio.run(test_course_handler())
