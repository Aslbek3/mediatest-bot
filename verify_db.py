import database
import sqlite3

# Run init_db to create indexes
database.init_db()

# Verify
conn = database.get_connection()
mode = conn.execute('PRAGMA journal_mode;').fetchone()[0]
print(f"Journal Mode: {mode}")

cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
indexes = [r[0] for r in cursor.fetchall()]
print(f"Indexes found: {indexes}")

conn.close()
