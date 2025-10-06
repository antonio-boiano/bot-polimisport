#!/usr/bin/env python3
"""
Database migration script to add is_fit_center column
"""

import sqlite3
import os

def migrate():
    db_path = 'polimisport.db'

    if not os.path.exists(db_path):
        print("❌ Database not found. Run setup.py first.")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(courses)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'is_fit_center' in columns:
            print("✅ Column 'is_fit_center' already exists. No migration needed.")
            conn.close()
            return True

        print("Adding 'is_fit_center' column to courses table...")

        # Add the column
        cursor.execute('ALTER TABLE courses ADD COLUMN is_fit_center INTEGER DEFAULT 0')

        conn.commit()
        print("✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Run: python refresh_courses.py")
        print("2. This will populate both courses and fit center slots")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        conn.close()
        return False

if __name__ == '__main__':
    migrate()
