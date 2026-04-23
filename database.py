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
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, embedding BLOB)''')
            
            # Migration: add email column to existing databases safely
            try:
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            except sqlite3.OperationalError:
                pass # Column already exists
            
            # Migration: add department column to existing databases safely
            try:
                conn.execute("ALTER TABLE users ADD COLUMN department TEXT")
            except sqlite3.OperationalError:
                pass # Column already exists
            
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

    def register_user(self, name, email, department, embedding):
        out = io.BytesIO()
        np.save(out, embedding)
        embedding_bytes = out.getvalue()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO users (name, email, department, embedding) VALUES (?, ?, ?, ?)", (name, email, department, embedding_bytes))

    def get_all_users(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT name, embedding FROM users")
            users = {}
            for name, emb_bytes in cursor.fetchall():
                users[name] = np.load(io.BytesIO(emb_bytes))
            return users

    def get_all_users_details(self):
        """Fetches detailed info for staff management"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT id, name, email, department FROM users")
            return [{"id": row[0], "name": row[1], "email": row[2] or "", "department": row[3] or ""} for row in cursor.fetchall()]

    def delete_user(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def update_user(self, user_id: int, name: str, email: str, department: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET name = ?, email = ?, department = ? WHERE id = ?", 
                (name, email, department, user_id)
            )

    # Updated: Now matches the columns created in init_db
    def get_attendance_logs(self):
        with sqlite3.connect(self.db_path) as conn:
            # Join with users to pull their email addresses
            cursor = conn.execute("""
                SELECT a.name, a.timestamp, a.status, u.email 
                FROM attendance_logs a
                LEFT JOIN users u ON a.name = u.name
                ORDER BY a.timestamp DESC
            """)
            return [{"name": row[0], "time": row[1], "status": row[2], "email": row[3] or "No Email"} for row in cursor.fetchall()]
        
    def get_attendance_logs_for_month(self, year: int, month: int):
        """Fetches attendance logs for a specific year and month."""
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT name, timestamp, status 
                FROM attendance_logs 
                WHERE strftime('%Y', timestamp) = ? AND strftime('%m', timestamp) = ?
                ORDER BY timestamp DESC
            """
            year_str = str(year)
            month_str = f"{month:02d}"
            
            cursor = conn.execute(query, (year_str, month_str))
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
        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # 3. Check for lateness (assuming 09:00 AM is the cutoff)
        actual_status = next_status
        if next_status == "IN":
            cutoff_time = now_dt.replace(hour=9, minute=0, second=0, microsecond=0)
            if now_dt > cutoff_time:
                actual_status = "IN (LATE)"
        
        # 4. Save the new status
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO attendance_logs (name, timestamp, status) VALUES (?, ?, ?)", 
                (name, now_str, actual_status)
            )
        return actual_status