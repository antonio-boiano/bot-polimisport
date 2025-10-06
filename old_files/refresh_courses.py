#!/usr/bin/env python3
"""
Course Scraper - Populates database with available courses
Run periodically (e.g., daily) to keep course data fresh
"""

import asyncio
import logging
import json
from database import Database
from scraper import CourseScraper
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class CourseRefresher:
    def __init__(self, config_path='../config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.db = Database()
        self.scraper = CourseScraper(self.config)

    async def refresh_courses(self):
        """Scrape and update course database"""
        logger.info("Starting course refresh...")

        try:
            # Get weekly schedule from website (both courses and fit center)
            schedule, schedule_fit = await self.scraper.get_weekly_schedule(headless=True)

            # Clear old courses
            logger.info("Clearing old course data...")
            self.db.clear_courses()

            # Track unique courses to avoid duplicates
            seen_courses = set()
            course_count = 0
            fit_count = 0

            # Process Corsi Platinum (courses)
            for day_name, courses in schedule.items():
                for course in courses:
                    # Create unique key to detect duplicates
                    unique_key = (
                        day_name,
                        course.get('time_start'),
                        course.get('skill'),
                        course.get('instructor'),
                        course.get('location_path')
                    )

                    # Skip if already seen
                    if unique_key in seen_courses:
                        logger.debug(f"Skipping duplicate: {unique_key}")
                        continue

                    seen_courses.add(unique_key)

                    # Add to database
                    self.db.add_course({
                        'name': course.get("course_type"),
                        'location': course.get('location_path'),
                        'day_of_week': course.get('weekday_it'),
                        'time_start': course.get('time_start'),
                        'time_end': course.get('time_end'),
                        'course_type': course.get('skill') if course.get('skill') else "",
                        'instructor': course.get('instructor'),
                        'is_fit_center': False
                    })

                    course_count += 1

            # Process Fit Center
            for day_name, courses in schedule_fit.items():
                for course in courses:
                    # Create unique key to detect duplicates
                    unique_key = (
                        day_name,
                        course.get('time_start'),
                        course.get('skill'),
                        course.get('instructor'),
                        course.get('location_path')
                    )

                    # Skip if already seen
                    if unique_key in seen_courses:
                        logger.debug(f"Skipping duplicate Fit Center: {unique_key}")
                        continue

                    seen_courses.add(unique_key)

                    # Add to database with fit_center flag
                    self.db.add_course({
                        'name': 'Fit Center',
                        'location': course.get('location_path'),
                        'day_of_week': course.get('weekday_it'),
                        'time_start': course.get('time_start'),
                        'time_end': course.get('time_end'),
                        'course_type': course.get('skill') if course.get('skill') else "",
                        'instructor': course.get('instructor'),
                        'is_fit_center': True
                    })

                    fit_count += 1

            logger.info(f"Course refresh completed: {course_count} courses + {fit_count} fit center slots added")
            return course_count + fit_count

        except Exception as e:
            logger.error(f"Course refresh failed: {e}")
            raise

    async def run(self):
        """Run the course refresh"""
        try:
            count = await self.refresh_courses()
            print(f"✅ Successfully refreshed {count} courses")
        except Exception as e:
            print(f"❌ Refresh failed: {e}")
            raise


async def main():
    refresher = CourseRefresher()
    await refresher.run()


if __name__ == '__main__':
    asyncio.run(main())
