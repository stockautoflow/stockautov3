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
                symbol TEXT PRIMARY KEY,
                size REAL NOT NULL,
                price REAL NOT NULL,
                entry_datetime TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                order_type TEXT NOT NULL,
                size REAL NOT NULL,
                price REAL,
                status TEXT NOT NULL
            )
        ''')
        self.conn.commit()
        print("データベーステーブルの初期化を確認しました。")

    def save_position(self, symbol, size, price, entry_datetime):
        """ポジション情報を保存または更新します。"""
        sql = "INSERT OR REPLACE INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (str(symbol), size, price, entry_datetime))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"ポジション保存エラー: {e}")

    def load_positions(self):
        """すべてのポジション情報を辞書として読み込みます。"""
        positions = {}
        sql = "SELECT symbol, size, price, entry_datetime FROM positions"
        try:
            cursor = self.conn.cursor()
            for row in cursor.execute(sql):
                positions[row[0]] = {
                    'size': row[1],
                    'price': row[2],
                    'entry_datetime': row[3]
                }
            return positions
        except sqlite3.Error as e:
            print(f"ポジション読み込みエラー: {e}")
            return {}

    def delete_position(self, symbol):
        """指定された銘柄のポジション情報を削除します。"""
        sql = "DELETE FROM positions WHERE symbol = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (str(symbol),))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"ポジション削除エラー: {e}")

    def save_order(self, order_id, symbol, order_type, size, price, status):
        """注文情報を保存または更新します。"""
        sql = "INSERT OR REPLACE INTO orders (order_id, symbol, order_type, size, price, status) VALUES (?, ?, ?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (order_id, str(symbol), order_type, size, price, status))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"注文保存エラー: {e}")

    def update_order_status(self, order_id, status):
        """特定の注文のステータスを更新します。"""
        sql = "UPDATE orders SET status = ? WHERE order_id = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (status, order_id))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"注文ステータス更新エラー: {e}")
            
    def load_orders(self):
        """すべての注文情報を辞書として読み込みます。"""
        orders = {}
        sql = "SELECT order_id, symbol, order_type, size, price, status FROM orders"
        try:
            cursor = self.conn.cursor()
            for row in cursor.execute(sql):
                orders[row[0]] = {
                    'symbol': row[1],
                    'order_type': row[2],
                    'size': row[3],
                    'price': row[4],
                    'status': row[5]
                }
            return orders
        except sqlite3.Error as e:
            print(f"注文読み込みエラー: {e}")
            return {}
            
    def close(self):
        if self.conn:
            self.conn.close()
            print("データベース接続をクローズしました。")