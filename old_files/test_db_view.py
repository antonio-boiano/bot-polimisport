#!/usr/bin/env python3
"""
Test script to verify database visualization
"""

from database import Database

db = Database()

# Get all courses
courses = db.get_all_courses()

print(f"Total courses in database: {len(courses)}")
print("\n" + "="*60)

# Group by day
days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']

for day_name in days:
    day_courses = [c for c in courses if c['day_of_week'] == day_name]
    if day_courses:
        print(f"\n📅 {day_name} ({len(day_courses)} corsi)")
        print("-" * 60)
        for idx, course in enumerate(day_courses, 1):
            print(f"{idx}. {course['course_type'] or course['name']}")
            print(f"   🕐 {course['time_start']} - {course['time_end']}")
            print(f"   📍 {course['location']}")
            if course['instructor']:
                print(f"   👤 {course['instructor']}")
            print()

print("\n" + "="*60)
print("✅ Database visualization test complete")
