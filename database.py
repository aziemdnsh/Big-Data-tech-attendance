import sqlite3
import numpy as np
import io
from datetime import datetime

class FaceDatabase:
    def __init__(self, db_path="attendance.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # 1. Face Data Table
            conn.execute('''CREATE TABLE IF NOT EXISTS users 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, embedding BLOB)''')
            
            # 2. Admin Table
            conn.execute('''CREATE TABLE IF NOT EXISTS admins 
                          (username TEXT PRIMARY KEY, password_hash TEXT)''')
            
            # 3. Attendance Logs Table (CRITICAL FIX)
            conn.execute('''CREATE TABLE IF NOT EXISTS attendance_logs 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, timestamp TEXT, status TEXT)''')
            
            conn.execute("INSERT OR IGNORE INTO admins (username, password_hash) VALUES (?, ?)", 
                         ("admin", "admin123"))

    def verify_admin(self, username, password):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM admins WHERE username = ? AND password_hash = ?", 
                                 (username, password))
            return cursor.fetchone() is not None

    def register_user(self, name, embedding):
        out = io.BytesIO()
        np.save(out, embedding)
        embedding_bytes = out.getvalue()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO users (name, embedding) VALUES (?, ?)", (name, embedding_bytes))

    def get_all_users(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT name, embedding FROM users")
            users = {}
            for name, emb_bytes in cursor.fetchall():
                users[name] = np.load(io.BytesIO(emb_bytes))
            return users

    # NEW: Function to save a new attendance record
    def log_attendance(self, name, status="VERIFIED"):
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO attendance_logs (name, timestamp, status) VALUES (?, ?, ?)", 
                         (name, now, status))

    # Updated: Now matches the columns created in init_db
    def get_attendance_logs(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT name, timestamp, status FROM attendance_logs ORDER BY timestamp DESC")
            return [{"name": row[0], "time": row[1], "status": row[2]} for row in cursor.fetchall()]
        
    def get_last_status(self, name):
        """Checks the most recent log for a specific user."""
        with sqlite3.connect(self.db_path) as conn:
        # We MUST filter by 'name' to get THAT person's last move
            cursor = conn.execute(
            "SELECT status FROM attendance_logs WHERE name = ? ORDER BY timestamp DESC LIMIT 1", 
            (name,)
            )
        row = cursor.fetchone()
        
        # If no history exists, or they last checked OUT, they are now coming IN
        if row is None or row[0] == "OUT":
            return "IN"
        # If they were already IN, they are now going OUT
        return "OUT"

    def log_attendance(self, name):
        # 1. Determine if this is an IN or OUT move
        next_status = self.get_last_status(name)
        
        # 2. Get current time
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 3. Save the new status
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO attendance_logs (name, timestamp, status) VALUES (?, ?, ?)", 
                (name, now, next_status)
            )
        return next_status