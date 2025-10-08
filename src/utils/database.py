"""
Database Manager - Low-level database operations
Handles SQLite database for courses and bookings
"""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class Database:
    """SQLite database handler for Polimisport data"""

    def __init__(self, db_path='polimisport.db'):
        self.db_path = db_path
        self._init_db()
        logger.info(f"Database initialized: {db_path}")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise e
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Courses table (includes both courses and fit center)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    day_of_week TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    course_type TEXT,
                    instructor TEXT,
                    is_fit_center INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(day_of_week, time_start, name, instructor, location)
                )
            ''')

            # User bookings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    booking_id TEXT UNIQUE,
                    course_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    booking_date TEXT NOT NULL,
                    booking_time TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Scheduled bookings - for bookings that need to be executed at midnight 2 days before
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER,
                    course_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    day_of_week TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    is_fit_center INTEGER DEFAULT 0,
                    target_date TEXT NOT NULL,
                    execution_time TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (course_id) REFERENCES courses(id)
                )
            ''')

            # Periodic bookings - recurring bookings with optional confirmation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS periodic_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER,
                    course_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    day_of_week TEXT NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    is_fit_center INTEGER DEFAULT 0,
                    requires_confirmation INTEGER DEFAULT 0,
                    confirmation_hours_before INTEGER DEFAULT 5,
                    cancel_hours_before INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    last_executed TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (course_id) REFERENCES courses(id)
                )
            ''')

            # Pending confirmations - tracks confirmations needed for periodic bookings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_confirmations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    periodic_booking_id INTEGER NOT NULL,
                    scheduled_booking_id INTEGER,
                    confirmation_message_id INTEGER,
                    target_date TEXT NOT NULL,
                    confirmation_deadline TIMESTAMP NOT NULL,
                    cancel_deadline TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (periodic_booking_id) REFERENCES periodic_bookings(id),
                    FOREIGN KEY (scheduled_booking_id) REFERENCES scheduled_bookings(id)
                )
            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_day ON courses(day_of_week)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_user ON user_bookings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_user ON scheduled_bookings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_status ON scheduled_bookings(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_execution ON scheduled_bookings(execution_time)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_periodic_user ON periodic_bookings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_periodic_active ON periodic_bookings(is_active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_confirmations_user ON pending_confirmations(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_confirmations_status ON pending_confirmations(status)')

    # ==================== COURSES ====================

    def add_course(self, course: Dict):
        """Add a course to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO courses
                (name, location, day_of_week, time_start, time_end, course_type, instructor, is_fit_center)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                course['name'],
                course['location'],
                course['day_of_week'],
                course['time_start'],
                course['time_end'],
                course.get('course_type'),
                course.get('instructor'),
                1 if course.get('is_fit_center') else 0
            ))

    def get_all_courses(self, include_fit_center: bool = False) -> List[Dict]:
        """Get all courses"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if include_fit_center:
                cursor.execute('SELECT * FROM courses ORDER BY day_of_week, time_start')
            else:
                cursor.execute('SELECT * FROM courses WHERE is_fit_center = 0 ORDER BY day_of_week, time_start')
            return [dict(row) for row in cursor.fetchall()]

    def get_fit_center_slots(self) -> List[Dict]:
        """Get all fit center slots"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM courses WHERE is_fit_center = 1 ORDER BY day_of_week, time_start')
            return [dict(row) for row in cursor.fetchall()]

    def clear_courses(self):
        """Clear all courses"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM courses')
            logger.info("Courses cleared from database")

    # ==================== BOOKINGS ====================

    def sync_user_bookings(self, user_id: int, bookings: List[Dict]):
        """Replace all user bookings with fresh scraped data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Clear existing bookings
            cursor.execute('DELETE FROM user_bookings WHERE user_id = ?', (user_id,))
            # Insert all new bookings
            for booking in bookings:
                cursor.execute('''
                    INSERT INTO user_bookings
                    (user_id, booking_id, course_name, location, booking_date, booking_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    booking['booking_id'],
                    booking['course_name'],
                    booking['location'],
                    booking['booking_date'],
                    booking['booking_time']
                ))

    def get_user_bookings(self, user_id: int, status: str = 'active') -> List[Dict]:
        """Get user bookings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM user_bookings
                WHERE user_id = ? AND status = ?
                ORDER BY booking_date, booking_time
            ''', (user_id, status))
            return [dict(row) for row in cursor.fetchall()]

    def update_booking_status(self, booking_id: str, status: str):
        """Update booking status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE user_bookings
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE booking_id = ?
            ''', (status, booking_id))

    def clear_bookings(self, user_id: int):
        """Clear all bookings for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM user_bookings WHERE user_id = ?', (user_id,))
            logger.info(f"Bookings cleared for user {user_id}")

    # ==================== SCHEDULED BOOKINGS ====================

    def add_scheduled_booking(self, booking: Dict) -> int:
        """Add a scheduled booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scheduled_bookings
                (user_id, course_id, course_name, location, day_of_week, time_start, time_end,
                 is_fit_center, target_date, execution_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                booking['user_id'],
                booking.get('course_id'),
                booking['course_name'],
                booking['location'],
                booking['day_of_week'],
                booking['time_start'],
                booking['time_end'],
                1 if booking.get('is_fit_center') else 0,
                booking['target_date'],
                booking['execution_time'],
                booking.get('status', 'pending')
            ))
            return cursor.lastrowid

    def get_scheduled_bookings(self, user_id: int = None, status: str = None) -> List[Dict]:
        """Get scheduled bookings with optional filters"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM scheduled_bookings WHERE 1=1'
            params = []

            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)

            query += ' ORDER BY execution_time'
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_scheduled_bookings(self) -> List[Dict]:
        """Get all pending scheduled bookings ready to execute"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM scheduled_bookings
                WHERE status = 'pending' AND execution_time <= datetime('now', 'localtime')
                ORDER BY execution_time
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def update_scheduled_booking_status(self, booking_id: int, status: str):
        """Update scheduled booking status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE scheduled_bookings
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, booking_id))

    def delete_scheduled_booking(self, booking_id: int):
        """Delete a scheduled booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM scheduled_bookings WHERE id = ?', (booking_id,))

    # ==================== PERIODIC BOOKINGS ====================

    def add_periodic_booking(self, booking: Dict) -> int:
        """Add a periodic booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO periodic_bookings
                (user_id, course_id, course_name, location, day_of_week, time_start, time_end,
                 is_fit_center, requires_confirmation, confirmation_hours_before, cancel_hours_before)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                booking['user_id'],
                booking.get('course_id'),
                booking['course_name'],
                booking['location'],
                booking['day_of_week'],
                booking['time_start'],
                booking['time_end'],
                1 if booking.get('is_fit_center') else 0,
                1 if booking.get('requires_confirmation') else 0,
                booking.get('confirmation_hours_before', 24),
                booking.get('cancel_hours_before', 2)
            ))
            return cursor.lastrowid

    def get_periodic_bookings(self, user_id: int = None, is_active: bool = True) -> List[Dict]:
        """Get periodic bookings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM periodic_bookings WHERE 1=1'
            params = []

            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if is_active is not None:
                query += ' AND is_active = ?'
                params.append(1 if is_active else 0)

            query += ' ORDER BY day_of_week, time_start'
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_active_periodic_bookings(self) -> List[Dict]:
        """Get all active periodic bookings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM periodic_bookings
                WHERE is_active = 1
                ORDER BY day_of_week, time_start
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def update_periodic_booking_last_executed(self, booking_id: int, timestamp: str):
        """Update last executed timestamp for periodic booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE periodic_bookings
                SET last_executed = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (timestamp, booking_id))

    def toggle_periodic_booking(self, booking_id: int, is_active: bool):
        """Enable or disable a periodic booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE periodic_bookings
                SET is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (1 if is_active else 0, booking_id))

    def delete_periodic_booking(self, booking_id: int):
        """Delete a periodic booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM periodic_bookings WHERE id = ?', (booking_id,))

    # ==================== PENDING CONFIRMATIONS ====================

    def add_pending_confirmation(self, confirmation: Dict) -> int:
        """Add a pending confirmation"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO pending_confirmations
                (user_id, periodic_booking_id, scheduled_booking_id, confirmation_message_id,
                 target_date, confirmation_deadline, cancel_deadline)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                confirmation['user_id'],
                confirmation['periodic_booking_id'],
                confirmation.get('scheduled_booking_id'),
                confirmation.get('confirmation_message_id'),
                confirmation['target_date'],
                confirmation['confirmation_deadline'],
                confirmation['cancel_deadline']
            ))
            return cursor.lastrowid

    def get_pending_confirmations(self, user_id: int = None, status: str = 'pending') -> List[Dict]:
        """Get pending confirmations"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM pending_confirmations WHERE 1=1'
            params = []

            if user_id is not None:
                query += ' AND user_id = ?'
                params.append(user_id)
            if status is not None:
                query += ' AND status = ?'
                params.append(status)

            query += ' ORDER BY confirmation_deadline'
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_confirmations_needing_action(self) -> List[Dict]:
        """Get confirmations that need to be sent or cancelled"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM pending_confirmations
                WHERE status = 'pending' AND (
                    (confirmation_message_id IS NULL AND confirmation_deadline <= datetime('now', 'localtime'))
                    OR cancel_deadline <= datetime('now', 'localtime')
                )
                ORDER BY confirmation_deadline
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def update_confirmation_status(self, confirmation_id: int, status: str):
        """Update confirmation status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE pending_confirmations
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, confirmation_id))

    def update_confirmation_message_id(self, confirmation_id: int, message_id: int):
        """Update confirmation message ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE pending_confirmations
                SET confirmation_message_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (message_id, confirmation_id))


if __name__ == '__main__':
    # Test database operations
    logging.basicConfig(level=logging.INFO)

    db = Database(':memory:')  # Use in-memory for testing

    print("✓ Database initialized")

    # Test adding course
    db.add_course({
        'name': 'Test Course',
        'location': 'Giuriati',
        'day_of_week': 'Lunedì',
        'time_start': '10:00',
        'time_end': '11:00',
        'course_type': 'YOGA',
        'instructor': 'Test Instructor',
        'is_fit_center': False
    })

    courses = db.get_all_courses()
    print(f"✓ Course added: {len(courses)} total")

    # Test adding booking
    db.add_user_booking(123, {
        'booking_id': 'test123',
        'course_name': 'YOGA',
        'location': 'Giuriati',
        'booking_date': '2025-10-15',
        'booking_time': '10:00'
    })

    bookings = db.get_user_bookings(123)
    print(f"✓ Booking added: {len(bookings)} total")

    print("\n✅ All database tests passed!")
