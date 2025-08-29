import sqlite3
import threading
from datetime import datetime
import os

class NotificationLogger:
    def __init__(self, db_path: str):
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self._db_path = db_path
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notification_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    recipient TEXT,
                    subject TEXT,
                    body TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT
                )
            ''')
            self.conn.commit()

    def log_request(self, priority: str, recipient: str, subject: str, body: str) -> int:
        sql = '''
            INSERT INTO notification_history (timestamp, priority, recipient, subject, body, status)
            VALUES (?, ?, ?, ?, ?, 'PENDING')
        '''
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(sql, (timestamp, priority, recipient, subject, body))
            self.conn.commit()
            return cursor.lastrowid

    def update_status(self, record_id: int, status: str, error_message: str = ""):
        sql = '''
            UPDATE notification_history
            SET status = ?, error_message = ?
            WHERE id = ?
        '''
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(sql, (status, error_message, record_id))
            self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()