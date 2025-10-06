"""
Booking Service - Advanced booking logic with instant, scheduled, and periodic bookings
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from enum import Enum

from ..utils import Database

logger = logging.getLogger(__name__)


class BookingMode(Enum):
    """Booking mode types"""
    INSTANT = "instant"  # Book immediately (within 2 days)
    SCHEDULED = "scheduled"  # Schedule for midnight 2 days before
    PERIODIC = "periodic"  # Recurring booking


class BookingService:
    """
    Advanced booking service handling multiple booking modes:
    - Instant: Book immediately if within 2 days
    - Scheduled: Auto-book at midnight 2 days before the course
    - Periodic: Recurring bookings with optional confirmation
    """

    def __init__(self, db: Database):
        self.db = db

    # ==================== COURSE DATE HELPERS ====================

    def get_next_date_for_day(self, day_name: str, weeks_ahead: int = 0) -> datetime:
        """
        Get next occurrence of a day of week

        Args:
            day_name: Italian day name (Lunedì, Martedì, etc.)
            weeks_ahead: Number of weeks to add (0 = this week or next)

        Returns:
            datetime object for the next occurrence
        """
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

        next_date = today + timedelta(days=days_ahead, weeks=weeks_ahead)
        return next_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def is_within_instant_booking_window(self, target_date: datetime) -> bool:
        """
        Check if date is within instant booking window (today, tomorrow, day after tomorrow)

        Args:
            target_date: Target date to check

        Returns:
            True if within 2 days
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days_difference = (target_date - today).days
        return 0 <= days_difference <= 2

    def calculate_execution_time(self, target_date: datetime) -> datetime:
        """
        Calculate when to execute a scheduled booking (midnight 2 days before)

        Args:
            target_date: Target course date

        Returns:
            Execution datetime (midnight 2 days before)
        """
        execution_date = target_date - timedelta(days=2)
        return execution_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # ==================== INSTANT BOOKING ====================

    def can_book_instantly(self, day_name: str) -> bool:
        """
        Check if a course can be booked instantly

        Args:
            day_name: Day of week

        Returns:
            True if within instant booking window
        """
        next_date = self.get_next_date_for_day(day_name)
        return self.is_within_instant_booking_window(next_date)

    def create_instant_booking_request(
        self,
        user_id: int,
        course: Dict,
        target_date: Optional[datetime] = None
    ) -> Dict:
        """
        Create an instant booking request (to be executed immediately)

        Args:
            user_id: User ID
            course: Course dictionary
            target_date: Optional specific target date

        Returns:
            Booking request dictionary
        """
        if target_date is None:
            target_date = self.get_next_date_for_day(course['day_of_week'])

        if not self.is_within_instant_booking_window(target_date):
            raise ValueError("Course is not within instant booking window (0-2 days)")

        return {
            'user_id': user_id,
            'course_id': course.get('id'),
            'course_name': course['name'],
            'location': course['location'],
            'day_of_week': course['day_of_week'],
            'time_start': course['time_start'],
            'time_end': course['time_end'],
            'is_fit_center': course.get('is_fit_center', False),
            'target_date': target_date.strftime('%Y-%m-%d'),
            'mode': BookingMode.INSTANT
        }

    # ==================== SCHEDULED BOOKING ====================

    def create_scheduled_booking(
        self,
        user_id: int,
        course: Dict,
        target_date: Optional[datetime] = None
    ) -> int:
        """
        Create a scheduled booking (auto-execute at midnight 2 days before)

        Args:
            user_id: User ID
            course: Course dictionary
            target_date: Optional specific target date

        Returns:
            Scheduled booking ID
        """
        if target_date is None:
            target_date = self.get_next_date_for_day(course['day_of_week'])

        execution_time = self.calculate_execution_time(target_date)

        booking_data = {
            'user_id': user_id,
            'course_id': course.get('id'),
            'course_name': course['name'],
            'location': course['location'],
            'day_of_week': course['day_of_week'],
            'time_start': course['time_start'],
            'time_end': course['time_end'],
            'is_fit_center': course.get('is_fit_center', False),
            'target_date': target_date.strftime('%Y-%m-%d'),
            'execution_time': execution_time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'pending'
        }

        booking_id = self.db.add_scheduled_booking(booking_data)
        logger.info(f"Scheduled booking created: ID {booking_id} for {target_date.strftime('%Y-%m-%d')}")
        return booking_id

    def get_user_scheduled_bookings(self, user_id: int, status: str = None) -> List[Dict]:
        """Get user's scheduled bookings"""
        return self.db.get_scheduled_bookings(user_id=user_id, status=status)

    def cancel_scheduled_booking(self, booking_id: int):
        """Cancel a scheduled booking"""
        self.db.delete_scheduled_booking(booking_id)
        logger.info(f"Scheduled booking {booking_id} cancelled")

    # ==================== PERIODIC BOOKING ====================

    def create_periodic_booking(
        self,
        user_id: int,
        course: Dict,
        requires_confirmation: bool = False,
        confirmation_hours_before: int = 5,
        cancel_hours_before: int = 1
    ) -> int:
        """
        Create a periodic (recurring) booking

        Args:
            user_id: User ID
            course: Course dictionary
            requires_confirmation: Whether to require confirmation before booking
            confirmation_hours_before: Hours before course to send confirmation (default 5)
            cancel_hours_before: Hours before course to auto-cancel if not confirmed (default 1)

        Returns:
            Periodic booking ID
        """
        booking_data = {
            'user_id': user_id,
            'course_id': course.get('id'),
            'course_name': course['name'],
            'location': course['location'],
            'day_of_week': course['day_of_week'],
            'time_start': course['time_start'],
            'time_end': course['time_end'],
            'is_fit_center': course.get('is_fit_center', False),
            'requires_confirmation': requires_confirmation,
            'confirmation_hours_before': confirmation_hours_before,
            'cancel_hours_before': cancel_hours_before
        }

        booking_id = self.db.add_periodic_booking(booking_data)
        logger.info(
            f"Periodic booking created: ID {booking_id} "
            f"(confirmation: {requires_confirmation})"
        )
        return booking_id

    def get_user_periodic_bookings(self, user_id: int, is_active: bool = True) -> List[Dict]:
        """Get user's periodic bookings"""
        return self.db.get_periodic_bookings(user_id=user_id, is_active=is_active)

    def toggle_periodic_booking(self, booking_id: int, is_active: bool):
        """Enable or disable a periodic booking"""
        self.db.toggle_periodic_booking(booking_id, is_active)
        logger.info(f"Periodic booking {booking_id} {'enabled' if is_active else 'disabled'}")

    def delete_periodic_booking(self, booking_id: int):
        """Delete a periodic booking"""
        self.db.delete_periodic_booking(booking_id)
        logger.info(f"Periodic booking {booking_id} deleted")

    # ==================== PERIODIC BOOKING PROCESSING ====================

    def process_periodic_bookings_for_week(self) -> List[Dict]:
        """
        Process all active periodic bookings and create scheduled bookings for next week

        Returns:
            List of created scheduled bookings
        """
        active_periodic = self.db.get_active_periodic_bookings()
        created_bookings = []

        for periodic in active_periodic:
            # Calculate next occurrence
            next_date = self.get_next_date_for_day(periodic['day_of_week'])

            # Check if we need to create a scheduled booking
            if not self.is_within_instant_booking_window(next_date):
                # Create scheduled booking
                execution_time = self.calculate_execution_time(next_date)

                scheduled_data = {
                    'user_id': periodic['user_id'],
                    'course_id': periodic['course_id'],
                    'course_name': periodic['course_name'],
                    'location': periodic['location'],
                    'day_of_week': periodic['day_of_week'],
                    'time_start': periodic['time_start'],
                    'time_end': periodic['time_end'],
                    'is_fit_center': periodic['is_fit_center'],
                    'target_date': next_date.strftime('%Y-%m-%d'),
                    'execution_time': execution_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'pending'
                }

                scheduled_id = self.db.add_scheduled_booking(scheduled_data)

                # If requires confirmation, create pending confirmation
                if periodic['requires_confirmation']:
                    self._create_confirmation_for_scheduled(
                        periodic,
                        scheduled_id,
                        next_date
                    )

                created_bookings.append({
                    'scheduled_id': scheduled_id,
                    'periodic_id': periodic['id'],
                    'target_date': next_date.strftime('%Y-%m-%d')
                })

        logger.info(f"Processed {len(active_periodic)} periodic bookings, created {len(created_bookings)} scheduled bookings")
        return created_bookings

    def _create_confirmation_for_scheduled(
        self,
        periodic: Dict,
        scheduled_id: int,
        target_date: datetime
    ):
        """
        Create a pending confirmation for a scheduled booking

        Args:
            periodic: Periodic booking dictionary
            scheduled_id: Scheduled booking ID
            target_date: Target course date
        """
        # Calculate confirmation deadline (e.g., 5 hours before course)
        course_time = datetime.strptime(periodic['time_start'], '%H:%M').time()
        course_datetime = target_date.replace(
            hour=course_time.hour,
            minute=course_time.minute
        )

        confirmation_deadline = course_datetime - timedelta(
            hours=periodic['confirmation_hours_before']
        )
        cancel_deadline = course_datetime - timedelta(
            hours=periodic['cancel_hours_before']
        )

        confirmation_data = {
            'user_id': periodic['user_id'],
            'periodic_booking_id': periodic['id'],
            'scheduled_booking_id': scheduled_id,
            'target_date': target_date.strftime('%Y-%m-%d'),
            'confirmation_deadline': confirmation_deadline.strftime('%Y-%m-%d %H:%M:%S'),
            'cancel_deadline': cancel_deadline.strftime('%Y-%m-%d %H:%M:%S')
        }

        self.db.add_pending_confirmation(confirmation_data)
        logger.info(
            f"Created confirmation for scheduled booking {scheduled_id}, "
            f"deadline: {confirmation_deadline}"
        )

    # ==================== CONFIRMATION HANDLING ====================

    def get_pending_confirmations(self, user_id: int) -> List[Dict]:
        """Get user's pending confirmations"""
        return self.db.get_pending_confirmations(user_id=user_id, status='pending')

    def confirm_booking(self, confirmation_id: int):
        """Confirm a booking (mark as confirmed)"""
        self.db.update_confirmation_status(confirmation_id, 'confirmed')
        logger.info(f"Confirmation {confirmation_id} confirmed")

    def reject_booking(self, confirmation_id: int):
        """Reject a booking (mark as rejected and cancel scheduled booking)"""
        # Get confirmation details
        confirmations = self.db.get_pending_confirmations()
        confirmation = next((c for c in confirmations if c['id'] == confirmation_id), None)

        if confirmation and confirmation.get('scheduled_booking_id'):
            # Cancel the scheduled booking
            self.db.update_scheduled_booking_status(
                confirmation['scheduled_booking_id'],
                'cancelled'
            )

        self.db.update_confirmation_status(confirmation_id, 'rejected')
        logger.info(f"Confirmation {confirmation_id} rejected")

    def get_confirmations_needing_action(self) -> List[Dict]:
        """Get confirmations that need to be sent or auto-cancelled"""
        return self.db.get_confirmations_needing_action()

    # ==================== BOOKING MODE DECISION ====================

    def suggest_booking_mode(self, day_name: str) -> BookingMode:
        """
        Suggest appropriate booking mode based on timing

        Args:
            day_name: Day of week

        Returns:
            Suggested booking mode
        """
        if self.can_book_instantly(day_name):
            return BookingMode.INSTANT
        else:
            return BookingMode.SCHEDULED

    def format_booking_info(self, booking: Dict) -> str:
        """Format booking for display"""
        return (
            f"{booking['course_name']} | "
            f"{booking['day_of_week']} {booking['time_start']}-{booking['time_end']} | "
            f"{booking['location']}"
        )


if __name__ == '__main__':
    # Test booking service
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("=== Booking Service Test ===\n")

    # Initialize
    db = Database(':memory:')
    service = BookingService(db)

    # Test course
    test_course = {
        'id': 1,
        'name': 'YOGA',
        'location': 'Giuriati',
        'day_of_week': 'Lunedì',
        'time_start': '18:00',
        'time_end': '19:00',
        'is_fit_center': False
    }

    user_id = 123456

    # Test 1: Check booking mode
    print("Test 1: Suggest booking mode")
    mode = service.suggest_booking_mode('Lunedì')
    print(f"✓ Suggested mode for Lunedì: {mode.value}\n")

    # Test 2: Create scheduled booking
    print("Test 2: Create scheduled booking")
    scheduled_id = service.create_scheduled_booking(user_id, test_course)
    print(f"✓ Created scheduled booking: ID {scheduled_id}")

    scheduled = service.get_user_scheduled_bookings(user_id)
    print(f"✓ User has {len(scheduled)} scheduled bookings\n")

    # Test 3: Create periodic booking with confirmation
    print("Test 3: Create periodic booking (with confirmation)")
    periodic_id = service.create_periodic_booking(
        user_id,
        test_course,
        requires_confirmation=True,
        confirmation_hours_before=5
    )
    print(f"✓ Created periodic booking: ID {periodic_id}")

    periodic = service.get_user_periodic_bookings(user_id)
    print(f"✓ User has {len(periodic)} periodic bookings\n")

    # Test 4: Create periodic booking without confirmation
    print("Test 4: Create periodic booking (no confirmation)")
    periodic_id2 = service.create_periodic_booking(
        user_id,
        {**test_course, 'day_of_week': 'Martedì'},
        requires_confirmation=False
    )
    print(f"✓ Created periodic booking: ID {periodic_id2}\n")

    # Test 5: Date calculations
    print("Test 5: Date calculations")
    next_monday = service.get_next_date_for_day('Lunedì')
    print(f"✓ Next Lunedì: {next_monday.strftime('%Y-%m-%d')}")

    can_instant = service.can_book_instantly('Lunedì')
    print(f"✓ Can book instantly: {can_instant}")

    exec_time = service.calculate_execution_time(next_monday)
    print(f"✓ Execution time (2 days before): {exec_time.strftime('%Y-%m-%d %H:%M')}\n")

    print("✅ All booking service tests passed!")
