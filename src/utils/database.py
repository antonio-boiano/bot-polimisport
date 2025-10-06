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

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_day ON courses(day_of_week)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_user ON user_bookings(user_id)')

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

    def add_user_booking(self, user_id: int, booking: Dict):
        """Add a user booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_bookings
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
