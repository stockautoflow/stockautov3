import sqlite3
import logging
import os

class StateManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self._create_tables()
            print(f"データベースに接続しました: {db_path}")
        except sqlite3.Error as e:
            print(f"データベース接続エラー: {e}")
            raise
    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY, size REAL NOT NULL,
                price REAL NOT NULL, entry_datetime TEXT NOT NULL)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
                order_type TEXT NOT NULL, size REAL NOT NULL,
                price REAL, status TEXT NOT NULL)
        ''')
        self.conn.commit()
        print("データベーステーブルの初期化を確認しました。")
    def close(self):
        if self.conn:
            self.conn.close()
            print("データベース接続をクローズしました。")