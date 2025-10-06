#!/usr/bin/env python3
"""
Migration script to add unique constraint to courses table
This recreates the courses table with the proper unique constraint
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def migrate_database(db_path='polimisport.db'):
    """Add unique constraint to courses table"""
    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='courses'")
        if not cursor.fetchone():
            print("✓ No courses table found, nothing to migrate")
            return

        # Backup existing data
        cursor.execute("SELECT * FROM courses")
        existing_courses = cursor.fetchall()
        print(f"Found {len(existing_courses)} existing courses")

        # Get column names
        cursor.execute("PRAGMA table_info(courses)")
        columns = [col[1] for col in cursor.fetchall()]

        # Drop old table
        cursor.execute("DROP TABLE courses")
        print("✓ Dropped old courses table")

        # Create new table with unique constraint
        cursor.execute('''
            CREATE TABLE courses (
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
        print("✓ Created new courses table with unique constraint")

        # Re-insert data (duplicates will be skipped)
        inserted = 0
        skipped = 0
        for row in existing_courses:
            try:
                cursor.execute('''
                    INSERT INTO courses
                    (name, location, day_of_week, time_start, time_end, course_type, instructor, is_fit_center, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', row[1:])  # Skip id column
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1

        print(f"✓ Inserted {inserted} unique courses, skipped {skipped} duplicates")

        # Create index
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_day ON courses(day_of_week)')
        print("✓ Created index")

        conn.commit()
        print("\n✅ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Migrate courses table to add unique constraint')
    parser.add_argument('--db', default='polimisport.db', help='Database path')
    args = parser.parse_args()

    migrate_database(args.db)
