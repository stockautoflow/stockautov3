import sqlite3
import logging
import os

# logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, db_path):
        """
        システムの稼働状態を永続化・復元するためのクラス。
        :param db_path: SQLiteデータベースファイルのパス。
        """
        self.db_path = db_path
        self.conn = None
        # DBファイルが置かれるディレクトリがなければ作成
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self._create_tables()
            # logger.info(f"データベースに接続しました: {db_path}")
            print(f"データベースに接続しました: {db_path}")
        except sqlite3.Error as e:
            # logger.error(f"データベース接続エラー: {e}")
            print(f"データベース接続エラー: {e}")
            raise

    def _create_tables(self):
        """必要なテーブルが存在しない場合に作成する。"""
        cursor = self.conn.cursor()
        # ポジション管理テーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                size REAL NOT NULL,
                price REAL NOT NULL,
                entry_datetime TEXT NOT NULL
            )
        ''')
        # 注文管理テーブル
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
        # logger.info("テーブルの初期化を確認しました。")
        print("データベーステーブルの初期化を確認しました。")

    def close(self):
        if self.conn:
            self.conn.close()
            # logger.info("データベース接続をクローズしました。")
            print("データベース接続をクローズしました。")