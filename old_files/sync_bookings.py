#!/usr/bin/env python3
"""
Booking Sync Script - Checks current bookings and syncs with database
Run periodically to keep booking data up to date
"""

import asyncio
import logging
import json
from database import Database
from booking import PolimisportBooker
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BookingSyncer:
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.db = Database()
        self.booker = PolimisportBooker(self.config)
        self.user_id = self.config['telegram']['allowed_user_id']

    async def sync_bookings(self):
        """Fetch current bookings from website and sync with database"""
        logger.info("Starting booking sync...")

        try:
            # Get bookings from website
            website_bookings = await self.booker.get_bookings()

            # Get bookings from database
            db_bookings = self.db.get_user_bookings(self.user_id, status='active')

            # Create sets of booking IDs
            website_booking_ids = {b['id'] for b in website_bookings}
            db_booking_ids = {b['booking_id'] for b in db_bookings}

            # Find new bookings (on website but not in DB)
            new_booking_ids = website_booking_ids - db_booking_ids

            # Find cancelled bookings (in DB but not on website)
            cancelled_booking_ids = db_booking_ids - website_booking_ids

            # Add new bookings to database
            for booking in website_bookings:
                if booking['id'] in new_booking_ids:
                    logger.info(f"Adding new booking: {booking['id']}")
                    self.db.add_user_booking(
                        user_id=self.user_id,
                        booking={
                            'booking_id': booking['id'],
                            'course_name': booking['course'],
                            'location': booking['location'],
                            'booking_date': booking.get('date', ''),
                            'booking_time': booking.get('time', '')
                        }
                    )

            # Update cancelled bookings in database
            for booking_id in cancelled_booking_ids:
                logger.info(f"Marking booking as cancelled: {booking_id}")
                self.db.update_booking_status(booking_id, 'cancelled')

            logger.info(
                f"Sync completed: {len(new_booking_ids)} new, "
                f"{len(cancelled_booking_ids)} cancelled, "
                f"{len(website_booking_ids)} total active"
            )

            return {
                'total': len(website_booking_ids),
                'new': len(new_booking_ids),
                'cancelled': len(cancelled_booking_ids)
            }

        except Exception as e:
            logger.error(f"Booking sync failed: {e}")
            raise

    async def run(self):
        """Run the booking sync"""
        try:
            result = await self.sync_bookings()
            print(f"✅ Sync completed:")
            print(f"   Total active: {result['total']}")
            print(f"   New: {result['new']}")
            print(f"   Cancelled: {result['cancelled']}")
        except Exception as e:
            print(f"❌ Sync failed: {e}")
            raise


async def main():
    syncer = BookingSyncer()
    await syncer.run()


if __name__ == '__main__':
    asyncio.run(main())
