#!/usr/bin/env python3
"""
Polimisport Booking Module
Handles booking operations using Playwright
"""

import logging
from playwright.async_api import async_playwright
from otp_extractor import get_otp_info
import time
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class PolimisportBooker:
    def __init__(self, config: dict):
        """Initialize the booker with configuration"""
        self.config = config
        self.username = config['username']
        self.password = config['password']
        self.otp_path = config['otpatu']

    async def _login(self, page):
        """Perform login to Polimisport website"""
        try:
            # Navigate to the website
            await page.goto('https://www.sport.polimi.it/')
            await page.get_by_role('link', name='Area Riservata').click()
            await page.get_by_role('button', name='Accedi al tuo account').click()

            # Fill in credentials
            await page.get_by_role('textbox', name='Codice Persona').click()
            await page.get_by_role('textbox', name='Codice Persona').fill(self.username)
            await page.get_by_role('textbox', name='Password').fill(self.password)
            await page.get_by_role('button', name='Accedi').click()

            # Handle OTP
            await page.get_by_role('textbox', name='OTP').click()

            otp_info = get_otp_info(self.otp_path)
            if otp_info['time_remaining'] < 2:
                logger.info("Waiting for new OTP code...")
                await page.wait_for_timeout(2000)
                otp_info = get_otp_info(self.otp_path)

            otp = otp_info['current_otp']
            await page.get_by_role('textbox', name='OTP').fill(otp)
            await page.get_by_role('button', name='Continua').click()

            # Wait for login to complete
            await page.wait_for_timeout(2000)

            logger.info("Login successful")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            raise

    async def make_booking(self, location: str, date: str = None, time_slot: str = None, headless: bool = True) -> Dict:
        """
        Make a booking at the specified location

        Args:
            location: Location identifier (e.g., 'giuriati_platinum')
            date: Date string (optional, defaults to today)
            time_slot: Time slot selector (optional)
            headless: Run browser in headless mode

        Returns:
            Dict with booking information
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()

            try:
                # Login
                await self._login(page)

                # Navigate to booking section
                await page.get_by_text('Booking Prenotazioni e noleggi View more').click()
                await page.get_by_role('link', name='Nuova Prenotazione').click()

                # Close info modal if present
                try:
                    await page.get_by_role('button', name='Chiudi questa informativa').click(timeout=2000)
                except:
                    pass

                # Select location
                if location == 'giuriati_platinum':
                    await page.get_by_role('link', name='Giuriati - Corsi Platinum').click()

                # Navigate to date
                await page.get_by_role('link', name='').click()  # Next week

                if date:
                    # TODO: Implement date selection logic
                    pass
                else:
                    # Book today
                    await page.get_by_role('link', name='Oggi').click()

                # Select time slot
                if time_slot:
                    # TODO: Implement time slot selection
                    await page.locator(time_slot).click()
                else:
                    # Default slot
                    await page.locator('div:nth-child(3) > div:nth-child(3) > .slot-notes.slot-notes-after').click()

                # Confirm booking
                await page.get_by_role('button', name='Conferma Prenotazione').click()
                await page.get_by_role('button', name='Sì').click()

                # Wait to see result
                await page.wait_for_timeout(3000)

                # Extract booking info (you'll need to adjust selectors)
                booking_info = {
                    'id': f"booking_{int(time.time())}",  # Placeholder
                    'location': location,
                    'datetime': date or datetime.now().strftime('%Y-%m-%d'),
                    'course': 'Corsi Platinum',
                    'status': 'confirmed'
                }

                logger.info(f"Booking created: {booking_info}")
                await browser.close()

                return booking_info

            except Exception as e:
                logger.error(f"Booking failed: {e}")
                await browser.close()
                raise

    async def get_bookings(self) -> List[Dict]:
        """
        Get list of current bookings

        Returns:
            List of booking dictionaries
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Login
                await self._login(page)

                # Navigate to bookings section
                await page.get_by_text('Booking Prenotazioni e noleggi View more').click()

                # Wait for bookings to load
                await page.wait_for_timeout(2000)

                # Extract booking information
                # TODO: Implement proper extraction based on page structure
                bookings = []

                # Placeholder logic - you'll need to adjust selectors
                try:
                    # Find all booking elements
                    booking_elements = await page.locator('.booking-item').all()  # Adjust selector

                    for element in booking_elements:
                        booking = {
                            'id': await element.get_attribute('data-booking-id'),  # Adjust
                            'course': await element.locator('.course-name').text_content(),  # Adjust
                            'datetime': await element.locator('.datetime').text_content(),  # Adjust
                            'location': await element.locator('.location').text_content(),  # Adjust
                        }
                        bookings.append(booking)
                except Exception as e:
                    logger.warning(f"Could not extract bookings: {e}")

                await browser.close()
                logger.info(f"Found {len(bookings)} bookings")

                return bookings

            except Exception as e:
                logger.error(f"Failed to get bookings: {e}")
                await browser.close()
                raise

    async def cancel_booking(self, booking_id: str) -> bool:
        """
        Cancel a specific booking

        Args:
            booking_id: ID of the booking to cancel

        Returns:
            True if successful, False otherwise
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Login
                await self._login(page)

                # Navigate to bookings
                await page.get_by_text('Booking Prenotazioni e noleggi View more').click()

                # Wait for page to load
                await page.wait_for_timeout(2000)

                # Find and click cancel button for specific booking
                # TODO: Implement proper cancellation logic based on page structure
                try:
                    # This is placeholder logic - adjust based on actual page structure
                    cancel_button = page.locator(f'[data-booking-id="{booking_id}"] .cancel-button')
                    await cancel_button.click()

                    # Confirm cancellation
                    await page.get_by_role('button', name='Conferma').click()

                    await page.wait_for_timeout(2000)

                    logger.info(f"Booking {booking_id} cancelled successfully")
                    await browser.close()
                    return True

                except Exception as e:
                    logger.error(f"Could not cancel booking: {e}")
                    await browser.close()
                    return False

            except Exception as e:
                logger.error(f"Cancellation failed: {e}")
                await browser.close()
                raise
