#!/usr/bin/env python3
"""
Test Database Operations
Interactive script to test database functionality
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import Database

print("=== Database Test ===\n")

# Create test database
db = Database(':memory:')
print("✓ Database initialized (in-memory)\n")

# Test adding courses
print(">>> Adding test courses...")
courses = [
    {
        'name': 'YOGA',
        'location': 'Giuriati',
        'day_of_week': 'Lunedì',
        'time_start': '10:00',
        'time_end': '11:00',
        'course_type': 'Platinum',
        'instructor': 'Mario Rossi',
        'is_fit_center': False
    },
    {
        'name': 'PILATES',
        'location': 'Giuriati',
        'day_of_week': 'Lunedì',
        'time_start': '11:00',
        'time_end': '12:00',
        'course_type': 'Platinum',
        'instructor': 'Luigi Verdi',
        'is_fit_center': False
    },
    {
        'name': 'Fit Center',
        'location': 'Sala Pesi',
        'day_of_week': 'Martedì',
        'time_start': '14:00',
        'time_end': '15:00',
        'course_type': None,
        'instructor': None,
        'is_fit_center': True
    }
]

for course in courses:
    db.add_course(course)

print(f"✓ Added {len(courses)} courses\n")

# Test retrieving courses
print(">>> Retrieving courses (excluding fit center)...")
all_courses = db.get_all_courses(include_fit_center=False)
print(f"✓ Found {len(all_courses)} courses:")
for c in all_courses:
    print(f"  - {c['day_of_week']} {c['time_start']}: {c['name']} ({c['instructor']})")

print()

# Test fit center retrieval
print(">>> Retrieving fit center slots...")
fit_slots = db.get_fit_center_slots()
print(f"✓ Found {len(fit_slots)} fit center slots:")
for s in fit_slots:
    print(f"  - {s['day_of_week']} {s['time_start']}: {s['location']}")

print()

# Test bookings
print(">>> Adding test booking...")
user_id = 123456
booking = {
    'booking_id': 'test_booking_001',
    'course_name': 'YOGA',
    'location': 'Giuriati',
    'booking_date': '2025-10-15',
    'booking_time': '10:00'
}

db.add_user_booking(user_id, booking)
print("✓ Booking added\n")

# Retrieve bookings
print(">>> Retrieving user bookings...")
user_bookings = db.get_user_bookings(user_id)
print(f"✓ Found {len(user_bookings)} bookings:")
for b in user_bookings:
    print(f"  - {b['booking_date']} {b['booking_time']}: {b['course_name']} @ {b['location']}")

print()

# Test booking status update
print(">>> Updating booking status...")
db.update_booking_status('test_booking_001', 'cancelled')
cancelled = db.get_user_bookings(user_id, status='cancelled')
print(f"✓ Updated status to 'cancelled': {len(cancelled)} cancelled bookings\n")

# Test clearing
print(">>> Testing clear operations...")
db.clear_bookings(user_id)
remaining = db.get_user_bookings(user_id)
print(f"✓ Cleared bookings: {len(remaining)} remaining\n")

db.clear_courses()
remaining_courses = db.get_all_courses(include_fit_center=True)
print(f"✓ Cleared courses: {len(remaining_courses)} remaining\n")

print("✅ All database tests passed!")
