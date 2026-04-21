import sqlite3

def get_connection():
    conn = sqlite3.connect("database.sqlite", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_blocked INTEGER DEFAULT 0
        )
    ''')
    # Migration: Add is_blocked to users if it doesn't exist
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column already exists
    # Movies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            description TEXT,
            video_file_id TEXT
        )
    ''')
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # Admins table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    # Indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_code ON movies(code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_name ON movies(name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_blocked ON users(is_blocked)')
    
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = get_connection()
    try:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def add_movie(code, name, description, video_file_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO movies (code, name, description, video_file_id)
            VALUES (?, ?, ?, ?)
        ''', (code, name, description, video_file_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_movie_by_code(code):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE code = ?", (code,))
    movie = cursor.fetchone()
    conn.close()
    return movie

def get_movies_by_name(name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE name LIKE ?", ('%' + name + '%',))
    movies = cursor.fetchall()
    conn.close()
    return movies

def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    return [u['user_id'] for u in users]

def get_movies_count():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM movies")
    count = cursor.fetchone()['cnt']
    conn.close()
    return count

def set_channel(channel_id, key='post_channel'):
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, channel_id))
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()

def get_all_movies():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code, name FROM movies ORDER BY CAST(code AS INTEGER), code")
    movies = cursor.fetchall()
    conn.close()
    return [{'code': m['code'], 'name': m['name']} for m in movies]

def get_channel(key='post_channel'):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Migration: if requested key is empty, check old channel_id
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            # Try old generic key
            cursor.execute("SELECT value FROM settings WHERE key = 'channel_id'")
            row = cursor.fetchone()
            if row:
                # Migrate to new key for future
                set_channel(row['value'], key)
                return row['value']
        return row['value'] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()

def set_admin_link(link):
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_link', ?)", (link,))
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()

def get_admin_link():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'admin_link'")
        row = cursor.fetchone()
        return row['value'] if row else "@coder_uzzz" # Default if not set
    except sqlite3.Error:
        return "@coder_uzzz"
    finally:
        conn.close()

def update_movie(code, name=None, description=None, video_file_id=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if name:
            cursor.execute("UPDATE movies SET name = ? WHERE code = ?", (name, code))
        if description:
            cursor.execute("UPDATE movies SET description = ? WHERE code = ?", (description, code))
        if video_file_id:
            cursor.execute("UPDATE movies SET video_file_id = ? WHERE code = ?", (video_file_id, code))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def delete_movie(code):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM movies WHERE code = ?", (code,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def add_admin(user_id):
    conn = get_connection()
    try:
        conn.execute("INSERT INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_admin(user_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def get_all_admins():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    admins = cursor.fetchall()
    conn.close()
    return [a['user_id'] for a in admins]

def is_db_admin(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def block_user(user_id):
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def unblock_user(user_id):
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()

def user_exists(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def is_user_blocked(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['is_blocked'] == 1 if row else False

def get_active_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
    users = cursor.fetchall()
    conn.close()
    return [u['user_id'] for u in users]

def get_blocked_users_count():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE is_blocked = 1")
    count = cursor.fetchone()['cnt']
    conn.close()
    return count


