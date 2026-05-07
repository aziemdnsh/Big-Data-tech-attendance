import mysql.connector
import numpy as np
import io
import hashlib
from datetime import datetime
from typing import Any, Optional, Tuple, List


class FaceDatabase:
    def __init__(self, host="localhost", user="root", password="Danish@123", database="attendance_db"):
        self.config = {
            "host": host,
            "user": user,
            "password": password
        }
        self.db_name = database
        self.init_db()

    def _get_connection(self):
        """Helper to get a connection pointing to our specific database."""
        return mysql.connector.connect(**self.config, database=self.db_name)

    def _execute(
        self,
        query: str,
        params: tuple = (),
        fetch: bool = False,
        fetchall: bool = False,
    ) -> Optional[Any]:
        """
        Centralized helper to execute queries, handle commits, and safely close connections.

        Returns:
            - fetchone() result (tuple | None) when fetch=True
            - fetchall() result (list[tuple]) when fetchall=True
            - None for INSERT / UPDATE / DELETE (commit only)
        """
        conn = self._get_connection()
        cursor = conn.cursor(buffered=True)
        try:
            cursor.execute(query, params)
            if fetch:
                return cursor.fetchone()       # tuple | None
            if fetchall:
                return cursor.fetchall()       # list[tuple]
            conn.commit()
            return None
        except mysql.connector.Error as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Typed wrappers — Pylance sees the concrete return types here,
    # eliminating all "Object of type None is not subscriptable" warnings.
    # ------------------------------------------------------------------

    def _fetch_one(self, query: str, params: tuple = ()) -> Optional[Tuple[Any, ...]]:
        """Execute a SELECT and return a single row, or None."""
        result = self._execute(query, params, fetch=True)
        return result  # type: ignore[return-value]

    def _fetch_all(self, query: str, params: tuple = ()) -> List[Tuple[Any, ...]]:
        """Execute a SELECT and return all rows (empty list if none)."""
        result = self._execute(query, params, fetchall=True)
        return result if result is not None else []  # type: ignore[return-value]

    def _write(self, query: str, params: tuple = ()) -> None:
        """Execute an INSERT / UPDATE / DELETE."""
        self._execute(query, params)

    def init_db(self):
        # Connect globally first to ensure the database exists
        conn = mysql.connector.connect(**self.config)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.db_name}`")
        conn.commit()
        cursor.close()
        conn.close()

        self._write('''
            CREATE TABLE IF NOT EXISTS users (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                name       VARCHAR(255)  NOT NULL,
                email      VARCHAR(255)  UNIQUE,
                department VARCHAR(255),
                embedding  LONGBLOB
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        self._write('''
            CREATE TABLE IF NOT EXISTS admins (
                username      VARCHAR(255) PRIMARY KEY,
                password_hash VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        self._write('''
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                name        VARCHAR(255) NOT NULL,
                `timestamp` DATETIME     NOT NULL,
                status      VARCHAR(50)  NOT NULL,
                INDEX idx_attendance_timestamp (`timestamp`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        self._write('''
            CREATE TABLE IF NOT EXISTS sites (
                id        INT AUTO_INCREMENT PRIMARY KEY,
                name      VARCHAR(255)   NOT NULL,
                latitude  DOUBLE         NOT NULL,
                longitude DOUBLE         NOT NULL,
                radius    INT            NOT NULL,
                is_active TINYINT(1)     NOT NULL DEFAULT 1
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')

        # Hash the default admin password instead of storing plain text
        hashed = hashlib.sha256("admin123".encode()).hexdigest()
        self._write(
            "INSERT IGNORE INTO admins (username, password_hash) VALUES (%s, %s)",
            ("admin", hashed)
        )

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #

    def verify_admin(self, username: str, password: str) -> bool:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        row = self._fetch_one(
            "SELECT 1 FROM admins WHERE username = %s AND password_hash = %s",
            (username, hashed)
        )
        return row is not None

    # ------------------------------------------------------------------ #
    # Users
    # ------------------------------------------------------------------ #

    def register_user(self, name: str, email: str, department: str, embedding: np.ndarray) -> None:
        out = io.BytesIO()
        np.save(out, embedding)
        self._write(
            "INSERT INTO users (name, email, department, embedding) VALUES (%s, %s, %s, %s)",
            (name, email, department, out.getvalue())
        )

    def get_all_users(self) -> dict:
        rows = self._fetch_all("SELECT name, embedding FROM users")
        users: dict = {}
        for name, emb_bytes in rows:
            if emb_bytes:
                # emb_bytes may be a memoryview from mysql-connector — convert first
                users[name] = np.load(io.BytesIO(bytes(emb_bytes)))
        return users

    def get_all_users_details(self) -> List[dict]:
        rows = self._fetch_all("SELECT id, name, email, department FROM users")
        return [
            {"id": row[0], "name": row[1], "email": row[2] or "", "department": row[3] or ""}
            for row in rows
        ]

    def delete_user(self, user_id: int) -> None:
        self._write("DELETE FROM users WHERE id = %s", (user_id,))

    def update_user(self, user_id: int, name: str, email: str, department: str) -> None:
        self._write(
            "UPDATE users SET name = %s, email = %s, department = %s WHERE id = %s",
            (name, email, department, user_id)
        )

    # ------------------------------------------------------------------ #
    # Attendance
    # ------------------------------------------------------------------ #

    def get_attendance_logs(self) -> List[dict]:
        rows = self._fetch_all("""
            SELECT a.name, a.`timestamp`, a.status, u.email
            FROM attendance_logs a
            LEFT JOIN users u ON a.name = u.name
            ORDER BY a.`timestamp` DESC
        """)
        return [
            {"name": row[0], "time": str(row[1]), "status": row[2], "email": row[3] or "No Email"}
            for row in rows
        ]

    def get_attendance_logs_for_month(self, year: int, month: int) -> List[dict]:
        rows = self._fetch_all("""
            SELECT name, `timestamp`, status
            FROM attendance_logs
            WHERE YEAR(`timestamp`) = %s AND MONTH(`timestamp`) = %s
            ORDER BY `timestamp` DESC
        """, (year, month))
        return [{"name": row[0], "time": str(row[1]), "status": row[2]} for row in rows]

    def get_attendance_logs_by_query(
        self, start_date: str, end_date: str, name: Optional[str] = None
    ) -> List[dict]:
        query = """
            SELECT name, `timestamp`, status
            FROM attendance_logs
            WHERE `timestamp` >= %s AND `timestamp` < DATE_ADD(%s, INTERVAL 1 DAY)
        """
        params: list = [start_date, end_date]
        if name and name != "All":
            query += " AND name = %s"
            params.append(name)
        query += " ORDER BY `timestamp` DESC"
        rows = self._fetch_all(query, tuple(params))
        return [{"name": row[0], "time": str(row[1]), "status": row[2]} for row in rows]

    def get_last_status(self, name: str) -> str:
        row = self._fetch_one(
            "SELECT status FROM attendance_logs WHERE name = %s ORDER BY `timestamp` DESC LIMIT 1",
            (name,)
        )
        if row is None or str(row[0]).startswith("OUT"):
            return "IN"
        return "OUT"

    def log_attendance(self, name: str) -> str:
        next_status = self.get_last_status(name)
        now_dt = datetime.now()
        actual_status = next_status
        if next_status == "IN":
            cutoff = now_dt.replace(hour=9, minute=0, second=0, microsecond=0)
            if now_dt > cutoff:
                actual_status = "IN (LATE)"
        self._write(
            "INSERT INTO attendance_logs (name, `timestamp`, status) VALUES (%s, %s, %s)",
            (name, now_dt.strftime("%Y-%m-%d %H:%M:%S"), actual_status)
        )
        return actual_status

    # ------------------------------------------------------------------ #
    # Sites
    # ------------------------------------------------------------------ #

    def add_site(self, name: str, latitude: float, longitude: float, radius: int) -> None:
        self._write(
            "INSERT INTO sites (name, latitude, longitude, radius) VALUES (%s, %s, %s, %s)",
            (name, latitude, longitude, radius)
        )

    def get_all_sites(self) -> List[dict]:
        rows = self._fetch_all(
            "SELECT id, name, latitude, longitude, radius, is_active FROM sites ORDER BY name"
        )
        return [
            {
                "id": row[0], "name": row[1],
                "latitude": row[2], "longitude": row[3],
                "radius": row[4], "is_active": bool(row[5])
            }
            for row in rows
        ]

    def get_active_sites(self) -> List[dict]:
        rows = self._fetch_all(
            "SELECT name, latitude, longitude, radius FROM sites WHERE is_active = 1"
        )
        return [{"name": row[0], "lat": row[1], "lon": row[2], "radius": row[3]} for row in rows]

    def update_site(
        self, site_id: int, name: str, latitude: float,
        longitude: float, radius: int, is_active: bool
    ) -> None:
        self._write(
            "UPDATE sites SET name=%s, latitude=%s, longitude=%s, radius=%s, is_active=%s WHERE id=%s",
            (name, latitude, longitude, radius, int(is_active), site_id)
        )

    def delete_site(self, site_id: int) -> None:
        self._write("DELETE FROM sites WHERE id = %s", (site_id,))
