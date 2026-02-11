"""Add use_ssh_fallback column to switches table if missing."""
import sqlite3
import os

# Get the database path - it's in the same directory as this script
db_path = os.path.join(os.path.dirname(__file__), 'mactraker.db')
print(f"Database path: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if column exists
cursor.execute("PRAGMA table_info(switches)")
columns = cursor.fetchall()
column_names = [col[1] for col in columns]

print(f"Existing columns: {column_names}")

if 'use_ssh_fallback' not in column_names:
    print("Adding use_ssh_fallback column...")
    cursor.execute("ALTER TABLE switches ADD COLUMN use_ssh_fallback BOOLEAN DEFAULT 0")
    conn.commit()
    print("Column added successfully!")
else:
    print("Column already exists.")

conn.close()
