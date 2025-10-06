"""
Booking Handler - Business logic for booking management
Handles booking operations and syncing with website
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from playwright.async_api import Page

from ..resources import SessionManager, WebScraper
from ..utils import Database

logger = logging.getLogger(__name__)


class BookingHandler:
    """Handles booking-related operations"""

    def __init__(self, db: Database, session: SessionManager):
        self.db = db
        self.session = session

    async def sync_bookings(self, user_id: int) -> int:
        """
        Sync bookings from website to database

        Args:
            user_id: Telegram user ID

        Returns:
            Number of bookings synced
        """
        logger.info(f"Syncing bookings for user {user_id}...")

        # Navigate to bookings page
        await self.session.page.get_by_text('Booking Prenotazioni e noleggi View more').click()
        await self.session.page.wait_for_timeout(3000)

        # Scrape bookings
        bookings = await self._scrape_current_bookings()

        # Store in database
        for booking in bookings:
            self.db.add_user_booking(user_id, booking)

        logger.info(f"Synced {len(bookings)} bookings")
        return len(bookings)

    async def _scrape_current_bookings(self) -> List[Dict]:
        """
        Scrape current bookings from bookings page

        Returns:
            List of booking dictionaries
        """
        html = await self.session.page.content()
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'lxml')
        bookings = []

        # Find booking entries in event-repository
        repository = soup.select_one('#event-repository')
        if not repository:
            logger.warning("No event-repository found")
            return bookings

        booking_els = repository.select('.event-main-block')
        logger.info(f"Found {len(booking_els)} booking elements")

        for idx, el in enumerate(booking_els):
            try:
                # Extract date
                date_el = el.select_one('.event-info-schedule')
                booking_date = date_el.get_text(strip=True) if date_el else None

                # Extract time
                time_start_el = el.select_one('.time-start')
                time_duration_el = el.select_one('.time-duration')
                time_start = time_start_el.get_text(strip=True) if time_start_el else None
                time_duration = time_duration_el.get_text(strip=True) if time_duration_el else None

                # Extract description and skill
                description_el = el.select_one('.event-info-description')
                skill_el = el.select_one('.event-info-skill-level')

                location = description_el.get_text(strip=True) if description_el else 'Unknown'
                course_name = skill_el.get_text(strip=True) if skill_el else 'Unknown'

                # Create unique booking ID
                booking_id = f"{booking_date}_{time_start}_{course_name}".replace('/', '-').replace(' ', '_').replace(':', '')

                if booking_date and time_start and course_name:
                    bookings.append({
                        'booking_id': booking_id,
                        'course_name': course_name,
                        'location': location,
                        'booking_date': booking_date,
                        'booking_time': f"{time_start} ({time_duration})" if time_duration else time_start
                    })
                    logger.info(f"Parsed booking {idx+1}: {course_name} on {booking_date} at {time_start}")
                else:
                    logger.warning(f"Incomplete booking data at index {idx}")

            except Exception as e:
                logger.error(f"Error parsing booking {idx}: {e}")

        return bookings

    async def create_booking(
        self,
        user_id: int,
        course_name: str,
        location: str,
        day: str,
        time_start: str,
        is_fit_center: bool = False
    ) -> bool:
        """
        Create a new booking

        Args:
            user_id: Telegram user ID
            course_name: Course name
            location: Location name
            day: Day of week
            time_start: Start time
            is_fit_center: Whether this is a fit center booking

        Returns:
            True if booking successful
        """
        logger.info(f"Creating booking: {course_name} on {day} at {time_start}")

        try:
            # Navigate to appropriate section
            if is_fit_center:
                await WebScraper.navigate_to_fit_center(self.session.page)
            else:
                await WebScraper.navigate_to_courses(self.session.page)

            # Find and click the slot
            success = await self._click_booking_slot(day, time_start, course_name)

            if success:
                # Confirm booking
                await self._confirm_booking()

                # Store in database
                booking = {
                    'booking_id': f"{day}_{time_start}_{course_name}".replace(' ', '_'),
                    'course_name': course_name,
                    'location': location,
                    'booking_date': self._get_next_date_for_day(day),
                    'booking_time': time_start
                }
                self.db.add_user_booking(user_id, booking)

                logger.info("Booking created successfully")
                return True
            else:
                logger.error("Failed to find booking slot")
                return False

        except Exception as e:
            logger.error(f"Booking error: {e}")
            return False

    async def _click_booking_slot(self, day: str, time: str, course_name: str) -> bool:
        """
        Find and click a booking slot

        Args:
            day: Day of week
            time: Start time
            course_name: Course name

        Returns:
            True if slot found and clicked
        """
        try:
            # Wait for slots to load
            await self.session.page.wait_for_selector('.event-slot', timeout=5000)

            # Find matching slot
            slots = await self.session.page.query_selector_all('.event-slot')

            for slot in slots:
                # Check if slot matches criteria
                time_el = await slot.query_selector('.time-start')
                desc_el = await slot.query_selector('.slot-description')

                if time_el and desc_el:
                    slot_time = await time_el.inner_text()
                    slot_desc = await desc_el.inner_text()

                    if slot_time.strip() == time and course_name.lower() in slot_desc.lower():
                        # Check if available
                        classes = await slot.get_attribute('class')
                        if 'slot-available' in classes:
                            await slot.click()
                            await self.session.page.wait_for_timeout(1000)
                            return True

            return False

        except Exception as e:
            logger.error(f"Error clicking slot: {e}")
            return False

    async def _confirm_booking(self):
        """Confirm booking in modal/popup"""
        try:
            # Look for confirm button
            confirm_btn = await self.session.page.wait_for_selector(
                'button:has-text("Conferma"), button:has-text("Prenota")',
                timeout=3000
            )
            if confirm_btn:
                await confirm_btn.click()
                await self.session.page.wait_for_timeout(2000)
        except Exception as e:
            logger.warning(f"Could not find confirm button: {e}")

    async def cancel_booking(self, booking_id: str) -> bool:
        """
        Cancel a booking

        Args:
            booking_id: Booking ID

        Returns:
            True if cancellation successful
        """
        logger.info(f"Canceling booking: {booking_id}")

        try:
            # Navigate to bookings page
            await self.session.page.goto('https://sport.polimi.it/bookings', wait_until='domcontentloaded')
            await self.session.page.wait_for_timeout(2000)

            # Find and click cancel button for this booking
            cancel_btn = await self.session.page.wait_for_selector(
                f'[data-booking-id="{booking_id}"] .cancel-btn, #{booking_id} .cancel-btn',
                timeout=5000
            )

            if cancel_btn:
                await cancel_btn.click()
                await self.session.page.wait_for_timeout(1000)

                # Confirm cancellation
                confirm = await self.session.page.wait_for_selector(
                    'button:has-text("Conferma"), button:has-text("Annulla prenotazione")',
                    timeout=3000
                )
                if confirm:
                    await confirm.click()
                    await self.session.page.wait_for_timeout(2000)

                # Update database
                self.db.update_booking_status(booking_id, 'cancelled')

                logger.info("Booking cancelled successfully")
                return True
            else:
                logger.error("Cancel button not found")
                return False

        except Exception as e:
            logger.error(f"Cancellation error: {e}")
            return False

    def get_user_bookings(self, user_id: int, status: str = 'active') -> List[Dict]:
        """
        Get user bookings from database

        Args:
            user_id: Telegram user ID
            status: Booking status filter

        Returns:
            List of booking dictionaries
        """
        return self.db.get_user_bookings(user_id, status)

    def format_booking_text(self, booking: Dict) -> str:
        """
        Format booking for display

        Args:
            booking: Booking dictionary

        Returns:
            Formatted string
        """
        return f"{booking['booking_date']} {booking['booking_time']} | {booking['course_name']} | {booking['location']}"

    def _get_next_date_for_day(self, day_name: str) -> str:
        """
        Get next date for a given day of week

        Args:
            day_name: Italian day name

        Returns:
            Date string (YYYY-MM-DD)
        """
        # Map Italian days to weekday numbers
        day_map = {
            'Lunedì': 0, 'Martedì': 1, 'Mercoledì': 2, 'Giovedì': 3,
            'Venerdì': 4, 'Sabato': 5, 'Domenica': 6
        }

        target_day = day_map.get(day_name, 0)
        today = datetime.now()
        current_day = today.weekday()

        days_ahead = (target_day - current_day) % 7
        if days_ahead == 0:
            days_ahead = 7

        from datetime import timedelta
        next_date = today + timedelta(days=days_ahead)
        return next_date.strftime('%Y-%m-%d')


if __name__ == '__main__':
    # Interactive test script
    import asyncio
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_booking_handler():
        """Test booking handler"""
        print("=== Booking Handler Test ===\n")

        # Check config
        config_path = 'config.json'
        if not Path(config_path).exists():
            print(f"❌ Config file not found: {config_path}")
            return

        # Initialize components
        db = Database(':memory:')
        user_id = 123456
        print("✓ Database initialized\n")

        async with SessionManager(config_path) as session:
            print("✓ Browser started")

            # Login
            if not await session.login():
                print("❌ Login failed")
                return
            print("✓ Login successful\n")

            # Create handler
            handler = BookingHandler(db, session)

            # Test sync bookings
            print(">>> Syncing bookings...")
            count = await handler.sync_bookings(user_id)
            print(f"✓ Synced {count} bookings\n")

            # Show bookings
            bookings = handler.get_user_bookings(user_id)
            if bookings:
                print(">>> Current bookings:")
                for b in bookings:
                    print(f"  - {handler.format_booking_text(b)}")
            else:
                print(">>> No bookings found")

            print("\n>>> Browser will stay open. Press Enter to close...")
            input()

        print("\n✅ Booking handler test passed!")

    asyncio.run(test_booking_handler())
