#!/usr/bin/env python3
"""
Comprehensive tests for Polimisport Bot
Tests database, OTP, scraping logic (mocked), and bot functions
"""

import unittest
import sqlite3
import os
import tempfile
import json
from datetime import datetime


class TestDatabase(unittest.TestCase):
    """Test database functionality"""

    def setUp(self):
        """Create temporary database for testing"""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.db_file.name
        self.db_file.close()

        # Import after creating temp file
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from polimisport_bot import Database
        self.Database = Database
        self.db = Database(self.db_path)

    def tearDown(self):
        """Clean up temporary database"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_database_initialization(self):
        """Test database tables are created"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        self.assertIn('courses', tables)
        self.assertIn('user_bookings', tables)

    def test_add_course(self):
        """Test adding a course"""
        course = {
            'name': 'Test Course',
            'location': 'Giuriati',
            'day_of_week': 'Lunedì',
            'time_start': '10:00',
            'time_end': '11:00',
            'course_type': 'YOGA',
            'instructor': 'Test Instructor',
            'is_fit_center': False
        }

        self.db.add_course(course)
        courses = self.db.get_all_courses()

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]['name'], 'Test Course')
        self.assertEqual(courses[0]['day_of_week'], 'Lunedì')

    def test_no_duplicate_courses(self):
        """Test that duplicate courses are handled correctly"""
        course = {
            'name': 'Test Course',
            'location': 'Giuriati',
            'day_of_week': 'Lunedì',
            'time_start': '10:00',
            'time_end': '11:00',
            'course_type': 'YOGA',
            'instructor': 'Test Instructor',
            'is_fit_center': False
        }

        # Add same course twice
        self.db.add_course(course)
        self.db.add_course(course)

        courses = self.db.get_all_courses()
        # Should only have one (OR REPLACE logic)
        self.assertEqual(len(courses), 1)

    def test_fit_center_separation(self):
        """Test fit center courses are separated"""
        course = {
            'name': 'Course',
            'location': 'Giuriati',
            'day_of_week': 'Lunedì',
            'time_start': '10:00',
            'time_end': '11:00',
            'course_type': 'YOGA',
            'instructor': 'Instructor',
            'is_fit_center': False
        }

        fit_center = {
            'name': 'Fit Center',
            'location': 'Giuriati',
            'day_of_week': 'Lunedì',
            'time_start': '11:00',
            'time_end': '12:00',
            'course_type': 'FREE',
            'instructor': None,
            'is_fit_center': True
        }

        self.db.add_course(course)
        self.db.add_course(fit_center)

        courses = self.db.get_all_courses(include_fit_center=False)
        fit_slots = self.db.get_fit_center_slots()

        self.assertEqual(len(courses), 1)
        self.assertEqual(len(fit_slots), 1)
        self.assertEqual(courses[0]['is_fit_center'], 0)
        self.assertEqual(fit_slots[0]['is_fit_center'], 1)

    def test_add_booking(self):
        """Test adding a user booking"""
        booking = {
            'booking_id': 'test123',
            'course_name': 'YOGA',
            'location': 'Giuriati',
            'booking_date': '2025-10-15',
            'booking_time': '10:00'
        }

        self.db.add_user_booking(123, booking)
        bookings = self.db.get_user_bookings(123)

        self.assertEqual(len(bookings), 1)
        self.assertEqual(bookings[0]['booking_id'], 'test123')

    def test_clear_courses(self):
        """Test clearing all courses"""
        course = {
            'name': 'Test',
            'location': 'Giuriati',
            'day_of_week': 'Lunedì',
            'time_start': '10:00',
            'time_end': '11:00',
            'course_type': 'YOGA',
            'instructor': 'Test',
            'is_fit_center': False
        }

        self.db.add_course(course)
        self.assertEqual(len(self.db.get_all_courses(include_fit_center=True)), 1)

        self.db.clear_courses()
        self.assertEqual(len(self.db.get_all_courses(include_fit_center=True)), 0)


class TestOTP(unittest.TestCase):
    """Test OTP generation"""

    def test_otp_generation(self):
        """Test OTP is generated from URL"""
        from polimisport_bot import get_otp_info

        # Sample OTP URL (this is a test secret, not real)
        test_url = "otpauth://totp/Test?secret=JBSWY3DPEHPK3PXP&issuer=Test"

        otp_info = get_otp_info(test_url)

        self.assertIn('current_otp', otp_info)
        self.assertIn('time_remaining', otp_info)
        self.assertEqual(len(otp_info['current_otp']), 6)
        self.assertGreater(otp_info['time_remaining'], 0)
        self.assertLessEqual(otp_info['time_remaining'], 30)


class TestHTMLParsing(unittest.TestCase):
    """Test HTML parsing functions"""

    def test_parse_weekly_pattern(self):
        """Test parsing weekly schedule from HTML"""
        from polimisport_bot import parse_weekly_pattern_from_html

        # Sample HTML (simplified)
        html = '''
        <div id="day-schedule-container">
            <div class="day-schedule">
                <div class="day-schedule-label">Lunedì, 10 Oct</div>
                <div class="day-schedule-slots">
                    <div class="event-slot slot-available">
                        <div class="slot-time">
                            <span class="time-start">10:00</span>
                            <span class="time-duration">55 min</span>
                        </div>
                        <div class="slot-description">Giuriati - Corsi Platinum - <span class="skill">YOGA</span></div>
                        <div class="slot-description2">con ROSSI MARIO</div>
                    </div>
                </div>
            </div>
        </div>
        '''

        result = parse_weekly_pattern_from_html(html)

        self.assertIn('Lunedì', result)
        self.assertGreater(len(result['Lunedì']), 0)

        event = result['Lunedì'][0]
        self.assertEqual(event['time_start'], '10:00')
        self.assertEqual(event['skill'], 'YOGA')
        self.assertEqual(event['instructor'], 'ROSSI MARIO')


class TestConfigValidation(unittest.TestCase):
    """Test configuration file validation"""

    def test_config_structure(self):
        """Test config.json has required fields"""
        config_path = os.path.join(os.path.dirname(__file__), '../config.json')

        if not os.path.exists(config_path):
            self.skipTest("config.json not found")

        with open(config_path) as f:
            config = json.load(f)

        # Check required fields
        self.assertIn('username', config)
        self.assertIn('password', config)
        self.assertIn('otpatu', config)
        self.assertIn('telegram', config)
        self.assertIn('bot_token', config['telegram'])
        self.assertIn('allowed_user_id', config['telegram'])


class TestIntegration(unittest.TestCase):
    """Integration tests (database + logic)"""

    def setUp(self):
        """Setup test environment"""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.db_file.name
        self.db_file.close()

        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from polimisport_bot import Database
        self.db = Database(self.db_path)

    def tearDown(self):
        """Cleanup"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_full_course_workflow(self):
        """Test adding courses, querying by day, clearing"""
        # Add courses for different days
        days = ['Lunedì', 'Martedì', 'Mercoledì']
        for day in days:
            for i in range(3):
                self.db.add_course({
                    'name': f'Course {i}',
                    'location': 'Giuriati',
                    'day_of_week': day,
                    'time_start': f'{10+i}:00',
                    'time_end': f'{11+i}:00',
                    'course_type': 'YOGA',
                    'instructor': 'Test',
                    'is_fit_center': False
                })

        # Should have 9 total courses
        all_courses = self.db.get_all_courses()
        self.assertEqual(len(all_courses), 9)

        # Check they're organized by day
        monday_courses = [c for c in all_courses if c['day_of_week'] == 'Lunedì']
        self.assertEqual(len(monday_courses), 3)

        # Clear and verify
        self.db.clear_courses()
        self.assertEqual(len(self.db.get_all_courses()), 0)

    def test_booking_workflow(self):
        """Test complete booking workflow"""
        user_id = 12345

        # Add bookings
        for i in range(3):
            self.db.add_user_booking(user_id, {
                'booking_id': f'book{i}',
                'course_name': f'Course {i}',
                'location': 'Giuriati',
                'booking_date': '2025-10-15',
                'booking_time': f'{10+i}:00'
            })

        # Get bookings
        bookings = self.db.get_user_bookings(user_id)
        self.assertEqual(len(bookings), 3)

        # Update status
        self.db.update_booking_status('book0', 'cancelled')
        bookings = self.db.get_user_bookings(user_id, status='active')
        self.assertEqual(len(bookings), 2)

        # Clear bookings
        self.db.clear_bookings(user_id)
        self.assertEqual(len(self.db.get_user_bookings(user_id)), 0)


def run_tests():
    """Run all tests"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestOTP))
    suite.addTests(loader.loadTestsFromTestCase(TestHTMLParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    exit(run_tests())
