#!/usr/bin/env python3
"""
Database models and schema for Polimisport bot
Uses SQLite for simple, file-based storage
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import json
from contextlib import contextmanager


class Database:
    def __init__(self, db_path='polimisport.db'):
        self.db_path = db_path
        self._init_db()

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
            raise e
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Courses table (populated by scraper)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    time_start TEXT NOT NULL,
                    time_end TEXT NOT NULL,
                    available_spots INTEGER,
                    total_spots INTEGER,
                    course_type TEXT,
                    instructor TEXT,
                    is_fit_center INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Booking actions queue (bot adds here, worker processes)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS booking_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,  -- 'book', 'cancel', 'check'
                    user_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
                    location TEXT,
                    course_name TEXT,
                    date TEXT,
                    time_slot TEXT,
                    booking_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    result TEXT,
                    error TEXT
                )
            ''')

            # User bookings (current active bookings)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    booking_id TEXT UNIQUE,
                    course_name TEXT NOT NULL,
                    location TEXT NOT NULL,
                    booking_date TEXT NOT NULL,
                    booking_time TEXT NOT NULL,
                    status TEXT DEFAULT 'active',  -- 'active', 'cancelled', 'completed'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Periodic bookings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS periodic_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT,
                    location TEXT NOT NULL,
                    course_name TEXT,
                    day_of_week INTEGER NOT NULL,
                    time_slot TEXT NOT NULL,
                    requires_confirmation INTEGER DEFAULT 1,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Pending confirmations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_confirmations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    periodic_booking_id INTEGER NOT NULL,
                    scheduled_for TIMESTAMP NOT NULL,
                    confirmed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (periodic_booking_id) REFERENCES periodic_bookings(id)
                )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_day ON courses(day_of_week)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_actions_status ON booking_actions(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_user ON user_bookings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_periodic_active ON periodic_bookings(active)')

    # ==================== COURSES ====================

    def add_course(self, course: Dict):
        """Add or update a course"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO courses
                (name, location, day_of_week, time_start, time_end, available_spots, total_spots, course_type, instructor, is_fit_center)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                course['name'],
                course['location'],
                course['day_of_week'],
                course['time_start'],
                course['time_end'],
                course.get('available_spots'),
                course.get('total_spots'),
                course.get('course_type'),
                course.get('instructor'),
                1 if course.get('is_fit_center') else 0
            ))

    def get_courses_by_day(self, day_of_week: int) -> List[Dict]:
        """Get all courses for a specific day"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM courses WHERE day_of_week = ? ORDER BY time_start', (day_of_week,))
            return [dict(row) for row in cursor.fetchall()]

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
        """Clear all courses (for refresh)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM courses')

    # ==================== BOOKING ACTIONS ====================

    def add_booking_action(self, action_type: str, user_id: int, **kwargs) -> int:
        """Add a booking action to the queue"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO booking_actions
                (action_type, user_id, location, course_name, date, time_slot, booking_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                action_type,
                user_id,
                kwargs.get('location'),
                kwargs.get('course_name'),
                kwargs.get('date'),
                kwargs.get('time_slot'),
                kwargs.get('booking_id')
            ))
            return cursor.lastrowid

    def get_pending_actions(self) -> List[Dict]:
        """Get all pending actions"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM booking_actions WHERE status = "pending" ORDER BY created_at')
            return [dict(row) for row in cursor.fetchall()]

    def update_action_status(self, action_id: int, status: str, result: str = None, error: str = None):
        """Update action status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            timestamp_field = 'started_at' if status == 'processing' else 'completed_at'

            cursor.execute(f'''
                UPDATE booking_actions
                SET status = ?, {timestamp_field} = CURRENT_TIMESTAMP, result = ?, error = ?
                WHERE id = ?
            ''', (status, result, error, action_id))

    def get_action_status(self, action_id: int) -> Optional[Dict]:
        """Get action status by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM booking_actions WHERE id = ?', (action_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # ==================== USER BOOKINGS ====================

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
        """Get user's bookings"""
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

    def delete_booking(self, booking_id: str):
        """Delete a booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM user_bookings WHERE booking_id = ?', (booking_id,))

    # ==================== PERIODIC BOOKINGS ====================

    def add_periodic_booking(self, user_id: int, booking: Dict) -> int:
        """Add a periodic booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO periodic_bookings
                (user_id, name, location, course_name, day_of_week, time_slot, requires_confirmation)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                booking.get('name'),
                booking['location'],
                booking.get('course_name'),
                booking['day_of_week'],
                booking['time_slot'],
                booking.get('requires_confirmation', 1)
            ))
            return cursor.lastrowid

    def get_periodic_bookings(self, user_id: int, active_only: bool = True) -> List[Dict]:
        """Get user's periodic bookings"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM periodic_bookings WHERE user_id = ?'
            if active_only:
                query += ' AND active = 1'
            cursor.execute(query, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_active_periodic_bookings(self) -> List[Dict]:
        """Get all active periodic bookings (for scheduler)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM periodic_bookings WHERE active = 1')
            return [dict(row) for row in cursor.fetchall()]

    def update_periodic_booking_status(self, booking_id: int, active: bool):
        """Activate or deactivate a periodic booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE periodic_bookings SET active = ? WHERE id = ?', (1 if active else 0, booking_id))

    def delete_periodic_booking(self, booking_id: int):
        """Delete a periodic booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM periodic_bookings WHERE id = ?', (booking_id,))

    # ==================== PENDING CONFIRMATIONS ====================

    def add_pending_confirmation(self, user_id: int, periodic_booking_id: int, scheduled_for: datetime, expires_at: datetime) -> int:
        """Add a pending confirmation"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO pending_confirmations
                (user_id, periodic_booking_id, scheduled_for, expires_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, periodic_booking_id, scheduled_for.isoformat(), expires_at.isoformat()))
            return cursor.lastrowid

    def get_pending_confirmations(self, user_id: int = None) -> List[Dict]:
        """Get pending confirmations"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute('SELECT * FROM pending_confirmations WHERE user_id = ? AND confirmed = 0', (user_id,))
            else:
                cursor.execute('SELECT * FROM pending_confirmations WHERE confirmed = 0')
            return [dict(row) for row in cursor.fetchall()]

    def confirm_booking(self, confirmation_id: int):
        """Confirm a pending booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE pending_confirmations SET confirmed = 1 WHERE id = ?', (confirmation_id,))

    def get_expired_confirmations(self) -> List[Dict]:
        """Get confirmations that have expired"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM pending_confirmations
                WHERE confirmed = 0 AND expires_at < CURRENT_TIMESTAMP
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def delete_confirmation(self, confirmation_id: int):
        """Delete a confirmation"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM pending_confirmations WHERE id = ?', (confirmation_id,))


if __name__ == '__main__':
    db = Database()
    print("Database initialized successfully.")
        
    print(db.get_all_courses())
    