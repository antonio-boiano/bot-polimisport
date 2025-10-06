"""
Booking Handler - Business logic for booking management
Handles booking operations and syncing with website
"""
import unicodedata
import logging
from typing import Dict, List, Optional
from datetime import datetime
import re
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
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
        await self.session.page.goto("https://ecomm.sportrick.com/sportpolimi/Booking")
        # await self.session.page.get_by_text('Booking Prenotazioni e noleggi View more').click()
        await self.session.page.wait_for_timeout(3000)

        # Scrape bookings
        bookings = await self._scrape_current_bookings()

        # Store in database (replace all existing bookings)
        self.db.sync_user_bookings(user_id, bookings)

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

                # Get course name from skill element, but it might be empty for Fit Center
                course_name = skill_el.get_text(strip=True) if skill_el else ''

                # For Fit Center bookings, skill element exists but is empty
                if not course_name:
                    # Try to extract from location/description (case-insensitive)
                    if location and 'fit center' in location.lower():
                        course_name = 'Fit Center'
                    else:
                        course_name = 'Unknown'

                # Create unique booking ID
                booking_id = f"{booking_date}_{time_start}_{course_name}".replace('/', '-').replace(' ', '_').replace(':', '')

                if booking_date and time_start:
                    bookings.append({
                        'booking_id': booking_id,
                        'course_name': course_name,
                        'location': location,
                        'booking_date': booking_date,
                        'booking_time': f"{time_start} ({time_duration})" if time_duration else time_start
                    })
                    logger.info(f"Parsed booking {idx+1}: {course_name} on {booking_date} at {time_start}")
                else:
                    logger.warning(f"Incomplete booking data at index {idx}: date={booking_date}, time={time_start}, course={course_name}")

            except Exception as e:
                logger.error(f"Error parsing booking {idx}: {e}")

        return bookings

    async def cancel_booking(self, user_id: int, booking_id: str) -> bool:
        """
        Cancel a booking by booking_id

        Args:
            user_id: Telegram user ID
            booking_id: Booking ID from database

        Returns:
            True if cancellation successful
        """
        logger.info(f"Cancelling booking {booking_id} for user {user_id}...")

        try:
            # Get booking info from database first
            bookings = self.db.get_user_bookings(user_id)
            booking_to_cancel = next((b for b in bookings if b['booking_id'] == booking_id), None)

            if not booking_to_cancel:
                logger.error(f"Booking {booking_id} not found in database")
                return False

            logger.info(f"Found booking to cancel: {booking_to_cancel['course_name']} on {booking_to_cancel['booking_date']} at {booking_to_cancel['booking_time']}")

            await self.session.page.goto("https://ecomm.sportrick.com/sportpolimi/Booking", wait_until='networkidle')
            await self.session.page.wait_for_timeout(2000)

            try:
                await self.session.page.get_by_role("button", name="Chiudi questa informativa").click(timeout=2000)
            except:
                pass
        
            # Find and click the cancel button for this specific booking
            # We need to identify the correct booking card by matching date, time, and course name
            logger.info("Looking for booking on page to cancel...")
            
            success = await self._find_and_cancel_booking(
                booking_to_cancel['booking_date'],
                booking_to_cancel['booking_time'].split(' ')[0],  # Extract just the time part
                booking_to_cancel['course_name']
            )
            
            logger.info(f"Cancellation attempt result: {success}")

            # Always refresh bookings from the page we're already on
            logger.info("Syncing bookings after cancellation attempt...")
            updated_bookings = await self._scrape_current_bookings()
            self.db.sync_user_bookings(user_id, updated_bookings)

            if success:
                logger.info(f"Booking {booking_id} cancelled successfully, synced {len(updated_bookings)} bookings")
                return True
            else:
                logger.error(f"Failed to cancel booking {booking_id}, synced {len(updated_bookings)} bookings anyway")
                return False

        except Exception as e:
            logger.error(f"Error cancelling booking: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _find_and_cancel_booking(self, date: str, time: str, course_name: str) -> bool:
        """
        Find a specific booking on the page and cancel it

        Args:
            date: Booking date (e.g., "07/10/2025")
            time: Booking time (e.g., "08:30")
            course_name: Course name

        Returns:
            True if cancellation successful
        """
        page = self.session.page

        try:
            # Wait for the event repository container to load
            await page.wait_for_selector('#event-repository', timeout=10000)
            logger.info("Event repository loaded")

            # Get all booking cards from the repository
            booking_cards = await page.query_selector_all('#event-repository .event-main-block')
            logger.info(f"Found {len(booking_cards)} booking cards on page")

            if len(booking_cards) == 0:
                logger.error("No booking cards found in #event-repository")
                # Debug: log page content
                html = await page.content()
                logger.debug(f"Page HTML length: {len(html)}")
                return False

            # Find the matching booking
            for idx, card in enumerate(booking_cards):
                # Extract card details
                card_date_el = await card.query_selector('.event-info-schedule')
                card_time_el = await card.query_selector('.time-start')
                card_course_el = await card.query_selector('.event-info-skill-level')
                card_location_el = await card.query_selector('.event-info-description')

                if not all([card_date_el, card_time_el]):
                    logger.warning(f"Card {idx} missing required elements (date or time)")
                    continue

                card_date = (await card_date_el.inner_text()).strip()
                card_time = (await card_time_el.inner_text()).strip()
                card_course = (await card_course_el.inner_text()).strip() if card_course_el else ''
                card_location = (await card_location_el.inner_text()).strip() if card_location_el else ''

                logger.info(f"Card {idx} raw: course='{card_course}' location='{card_location}' date='{card_date}' time='{card_time}'")

                # For Fit Center bookings, course name is empty - use location instead (case-insensitive check)
                if not card_course and 'fit center' in card_location.lower():
                    card_course = 'Fit Center'
                    logger.info(f"  -> Set course to 'Fit Center' based on location")

                logger.info(f"Card {idx} final: course='{card_course}' date='{card_date}' time='{card_time}'")

                # Match booking (normalize course names for comparison)
                date_match = card_date == date
                time_match = card_time == time
                course_match = self._norm(card_course) == self._norm(course_name)

                logger.info(f"  Matching against: course='{course_name}' date='{date}' time='{time}'")
                logger.info(f"  Normalized comparison: '{self._norm(card_course)}' == '{self._norm(course_name)}' = {course_match}")
                logger.info(f"  Match results: date={date_match}, time={time_match}, course={course_match}")

                if date_match and time_match and course_match:
                    logger.info(f"Found matching booking card at index {idx}")

                    # Find and click the cancel button within this card
                    cancel_button = await card.query_selector('button.btn-delete')
                    if not cancel_button:
                        logger.error("Cancel button not found in booking card")
                        return False

                    logger.info("Clicking cancel button...")
                    await cancel_button.click()
                    await page.wait_for_timeout(1500)

                    # Confirm cancellation - click "Sì" button
                    try:
                        logger.info("Looking for confirmation dialog...")
                        await page.get_by_role('button', name='Sì').click()
                        await page.wait_for_timeout(1500)

                        # Click "Ok" to close confirmation dialog
                        logger.info("Clicking OK...")
                        await page.get_by_role('button', name='Ok').click()
                        await page.wait_for_timeout(1500)

                        logger.info("Cancellation confirmed")
                        return True
                    except Exception as e:
                        logger.error(f"Error during confirmation: {e}")
                        return False

            logger.warning(f"No matching booking found for {course_name} on {date} at {time}")
            logger.info(f"Looking for: date={date}, time={time}, course={self._norm(course_name)}")
            return False

        except Exception as e:
            logger.error(f"Error finding and cancelling booking: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

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

            logger.info("Navigation complete")

            # Find and click the slot
            success = await self._click_booking_slot(day, time_start, course_name)

            if success:
                # Confirm booking
                await self._confirm_booking(user_id)

                # # Store in database
                # booking = {
                #     'booking_id': f"{day}_{time_start}_{course_name}".replace(' ', '_'),
                #     'course_name': course_name,
                #     'location': location,
                #     'booking_date': self._get_next_date_for_day(day),
                #     'booking_time': time_start
                # }
                # self.db.add_user_booking(user_id, booking)

                logger.info("Booking created successfully")
                return True
            else:
                logger.error("Failed to find booking slot")
                return False

        except Exception as e:
            logger.error(f"Booking error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _norm(self,s: str) -> str:
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", s.strip().lower())

    async def _click_booking_slot(self, day: str, time: str, course_name: str) -> bool:
        """
        Clicks the 'Prenota' of the requested slot (by day, HH:MM and course name).
        Tries multiple strategies to avoid flakiness/overlays.
        """
        page = self.session.page
        try:
            logger.info(f"Current URL: {page.url}")

            # 1) Wait for calendar & headers
            await page.wait_for_selector('#booking-calendar', state='visible', timeout=15000)
            headers = page.locator('.day-column h3.day-schedule-label')
            await headers.first.wait_for(state='attached', timeout=15000)
            header_texts = await headers.all_inner_texts()
            logger.info(f"Found day headers: {header_texts}")

            # 2) Find the day column (accent-insensitive, prefix match)
            norm_day = self._norm(day)
            day_idx = None
            for i, txt in enumerate(header_texts):
                if self._norm(txt).startswith(norm_day):
                    day_idx = i
                    break
            logger.info(f"Matched day '{day}' to header index: {day_idx}")
            if day_idx is None:
                logger.warning(f"No day column found for header starting with '{day}'.")
                return False

            day_column = page.locator('.day-column').nth(day_idx)
            await day_column.wait_for(state='attached', timeout=10000)

            # 3) Build a precise slot locator (time + course)
            #    We use :has() to keep the locator "live" and robust.

            # First try: exact match with time and course name
            slot = day_column.locator(
                f".event-slot.slot-available"
                f":has(.time-start:text-is('{time}'))"
                f":has(.skill:has-text('{course_name}'))"
            )

            slot_count = await slot.count()
            logger.info(f"Found {slot_count} slots matching time={time} and course={course_name}")

            # If no exact match, try with just time (for Fit Center which might not have skill label)
            if slot_count == 0:
                logger.info("Trying to match by time only (for Fit Center)...")
                slot = day_column.locator(
                    f".event-slot.slot-available"
                    f":has(.time-start:text-is('{time}'))"
                )
                slot_count = await slot.count()
                logger.info(f"Found {slot_count} slots matching time={time}")

            # If still no match, try partial time match
            if slot_count == 0:
                logger.info("Trying partial time match...")
                slot = day_column.locator(
                    f".event-slot.slot-available"
                    f":has(.time-start:has-text('{time}'))"
                )
                slot_count = await slot.count()
                logger.info(f"Found {slot_count} slots with partial time match")

            if slot_count == 0:
                # Debug: show all available slots in this day
                all_slots = await day_column.locator(".event-slot.slot-available").all()
                logger.warning(f"Found {len(all_slots)} total available slots in {day}")
                for i, s in enumerate(all_slots[:5]):  # Show first 5
                    time_el = await s.locator(".time-start").first.inner_text() if await s.locator(".time-start").count() > 0 else "N/A"
                    skill_el = await s.locator(".skill").first.inner_text() if await s.locator(".skill").count() > 0 else "N/A"
                    logger.info(f"  Slot {i+1}: time={time_el}, skill={skill_el}")

                logger.warning(f"No available slot found for {course_name} at {time} in '{day}'.")
                return False

            slot = slot.first
            await slot.scroll_into_view_if_needed()
            # If it's rendered but offscreen/covered, keep waiting until it's actually visible.
            try:
                await slot.wait_for(state='visible', timeout=3000)
            except PlaywrightTimeoutError:
                # Not fatal; continue with click fallbacks.
                pass

            # 4) Prefer the visible 'Prenota' label.
            #    Many layouts have both '.slot-notes-before' and '.slot-notes-after'.
            prenota_after = slot.locator(".slot-notes.slot-notes-after", has_text="Prenota").first
            prenota_before = slot.locator(".slot-notes.slot-notes-before", has_text="Prenota").first

            # Helper: try clicking a locator with increasing aggression.
            async def try_click(loc):
                if await loc.count() == 0:
                    return False
                try:
                    # First, a normal click
                    await loc.click(timeout=2000)
                    return True
                except Exception as e1:
                    logger.debug(f"Normal click failed: {e1}")
                try:
                    # If something overlaps, scroll and force-click
                    await loc.scroll_into_view_if_needed()
                    await loc.click(timeout=2000, force=True)
                    return True
                except Exception as e2:
                    logger.debug(f"Force click failed: {e2}")
                try:
                    # JS click as last resort (avoids hit-testing issues)
                    handle = await loc.element_handle()
                    if handle:
                        await page.evaluate("(el) => el.click()", handle)
                        return True
                except Exception as e3:
                    logger.debug(f"JS click failed: {e3}")
                return False

            # 5) Click attempts in order of reliability
            clicked = (
                await try_click(prenota_after)
                or await try_click(prenota_before)
                or await try_click(slot)  # click whole slot if labels are funky
                or await try_click(slot.locator(".slot-description"))  # click the text row (often works)
                or await try_click(slot.locator(f".slot-description:has-text('{course_name}')"))
            )

            if not clicked:
                # Absolute, page-level fallbacks (based on your manual test)
                try:
                    # Target any visible 'Prenota' inside the matched slot via :scope
                    any_prenota = slot.locator(":scope .slot-notes:has-text('Prenota')").first
                    await any_prenota.click(timeout=2000, force=True)
                    clicked = True
                except Exception as e:
                    logger.debug(f"Scope Prenota fallback failed: {e}")

            if not clicked:
                logger.warning("All click strategies failed.")
                return False

            logger.info("Clicked the slot, waiting for confirmation...")

            # 6) Post-click: wait for some confirmation signal, but don't fail if UI is slow.
            #    Adjust these to whatever your app shows after clicking.
            confirmed = False
            try:
                # A container that appears/turns visible after booking
                confirm_box = page.locator("#booking-confirm-container")
                await confirm_box.wait_for(state="visible", timeout=4000)
                confirmed = True
            except PlaywrightTimeoutError:
                # Alternative: the slot might flip state or a confirmation text appears
                try:
                    await page.locator("text=Prenotazione confermata").first.wait_for(state="visible", timeout=2000)
                    confirmed = True
                except PlaywrightTimeoutError:
                    pass

            logger.info("Slot clicked successfully" + (" (confirmed)" if confirmed else " (no explicit confirmation yet)"))
            # If the click succeeded without throwing, return True even if confirmation didn’t appear yet.
            return True

        except PlaywrightTimeoutError as e:
            logger.error(f"Timeout while waiting for elements: {e}")
            return False
        except Exception as e:
            logger.error(f"Error clicking slot: {e}", exc_info=True)
            return False

    async def _confirm_booking(self, user_id: int):
        """Confirm booking in confirmation page"""
        try:
            # Wait for the confirmation container to appear
            await self.session.page.wait_for_selector('#booking-confirm-container', timeout=5000)
            logger.info("Booking confirmation page loaded")

            # Wait a moment for the page to fully render
            await self.session.page.wait_for_timeout(1000)

            # Look for the confirm button by ID (most reliable)
            confirm_btn = await self.session.page.wait_for_selector(
                '#btnConfirmAppointmentBooking',
                timeout=5000
            )

            if confirm_btn:
                logger.info("Found confirm button, clicking...")
                await confirm_btn.click()
                await self.session.page.wait_for_timeout(1000)
                await self.session.page.get_by_text("No", exact=True).click()
                await self.session.page.wait_for_timeout(2000)
                logger.info("Booking confirmed!")
                
                # Scrape bookings
                bookings = await self._scrape_current_bookings()

                # Store in database (replace all existing bookings)
                self.db.sync_user_bookings(user_id, bookings)

                logger.info(f"Synced {len(bookings)} bookings")
                
            else:
                logger.error("Confirm button not found")

        except Exception as e:
            logger.error(f"Error confirming booking: {e}")
            import traceback
            logger.error(traceback.format_exc())

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
