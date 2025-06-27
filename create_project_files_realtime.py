# ==============================================================================
# ファイル: create_project_files_realtime.py
# 説明: このスクリプトは、リアルタイム自動トレードシステムに
#       必要な「新規」ファイルとディレクトリの骨格のみを生成します。
#       既存ファイルは変更しません。
# バージョン: v6.0
# 主な変更点:
#   - realtrade/state_manager.py: DBへの保存・読込メソッドを実装
#   - run_realtrade.py: StateManagerの動作確認テストを追加
# ==============================================================================
import os

project_files_realtime = {
    # --- ▼▼▼ リアルタイムシステム用のファイル ▼▼▼ ---

    ".env.example": """# このファイルをコピーして .env という名前のファイルを作成し、
# 実際のAPIキーに書き換えてください。
# .env ファイルは .gitignore に追加し、バージョン管理に含めないでください。

API_KEY="YOUR_API_KEY_HERE"
API_SECRET="YOUR_API_SECRET_HERE"
""",

    "config_realtrade.py": """import os
import logging

# --- API認証情報 ---
# .envファイルから読み込まれた環境変数を取得します。
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# --- 必須設定の検証 ---
if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
    print("警告: 環境変数 'API_KEY' が設定されていません。")
if not API_SECRET or API_SECRET == "YOUR_API_SECRET_HERE":
    print("警告: 環境変数 'API_SECRET' が設定されていません。")

# --- 銘柄・戦略設定 ---
RECOMMEND_FILE_PATTERN = "all_recommend_*.csv"

# --- 安全装置設定 ---
MAX_ORDER_SIZE_JPY = 1000000
MAX_CONCURRENT_ORDERS = 5
EMERGENCY_STOP_THRESHOLD = -0.1

# --- データベース設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "realtrade", "db", "realtrade_state.db")

print("設定ファイルをロードしました (config_realtrade.py)")
""",

    "run_realtrade.py": """import logging
import schedule
import time
import yaml
import pandas as pd
import glob
from datetime import datetime
import os
from dotenv import load_dotenv

# --- .envファイルから環境変数をロード ---
load_dotenv()

import config_realtrade as config
# import logger_setup
# import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.mock.broker import MockBrokerBridge
from realtrade.mock.data_fetcher import MockDataFetcher

# logger_setup.setup_logging()
# logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        print("リアルタイムトレーダーを初期化中...")
        if not config.API_KEY or not config.API_SECRET:
            print("エラー: APIキーまたはシークレットが設定されていません。")
            raise ValueError("APIキーが設定されていません。")

        # モック用のダミー銘柄リスト
        self.symbols = [1301, 7203] 
        print(f"対象銘柄: {self.symbols}")

        # 各モジュールの初期化
        self.state_manager = StateManager(config.DB_PATH)
        self.broker = MockBrokerBridge(config=config)
        self.data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
        
        # self.cerebro = self._setup_cerebro()
        self.is_running = False

    def _test_state_manager(self):
        \"\"\"StateManagerの動作を確認するためのテストメソッド。\"\"\"
        print("\\n--- StateManagerテスト開始 ---")
        try:
            # ポジションのテスト
            print("1. ポジション情報を保存します...")
            dt_now = datetime.now().isoformat()
            self.state_manager.save_position('1301', 100, 2500.5, dt_now)
            self.state_manager.save_position('7203', -50, 8800.0, dt_now)
            
            print("2. ポジション情報を読み込みます...")
            positions = self.state_manager.load_positions()
            print("読み込んだポジション:", positions)
            assert len(positions) == 2
            assert positions['1301']['size'] == 100

            # 注文のテスト
            print("3. 注文情報を保存します...")
            self.state_manager.save_order('order-001', '1301', 'buy_limit', 100, 2400.0, 'submitted')
            
            print("4. 注文情報を更新します...")
            self.state_manager.update_order_status('order-001', 'accepted')

            print("5. 注文情報を読み込みます...")
            orders = self.state_manager.load_orders()
            print("読み込んだ注文:", orders)
            assert orders['order-001']['status'] == 'accepted'

            print("6. ポジションを削除します...")
            self.state_manager.delete_position('7203')
            positions = self.state_manager.load_positions()
            print("削除後のポジション:", positions)
            assert '7203' not in positions
            
            print("--- StateManagerテスト正常終了 ---")
        except Exception as e:
            print(f"--- StateManagerテスト中にエラーが発生しました: {e} ---")


    def start(self):
        print("システムを開始します。")
        self.broker.start()
        self.data_fetcher.start()

        # 動作確認
        self._test_state_manager()

        self.is_running = True
        print("\\nシステムは起動状態です。Ctrl+Cで終了します。")


    def stop(self):
        print("システムを停止します。")
        if hasattr(self, 'broker'): self.broker.stop()
        if hasattr(self, 'data_fetcher'): self.data_fetcher.stop()
        if hasattr(self, 'state_manager'): self.state_manager.close()
        self.is_running = False
        print("システムが正常に停止しました。")

if __name__ == '__main__':
    print("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\\nCtrl+Cを検知しました。")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
    finally:
        if trader:
            trader.stop()
""",

    "realtrade/state_manager.py": """import sqlite3
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
        \"\"\"ポジション情報を保存または更新します。\"\"\"
        sql = "INSERT OR REPLACE INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (str(symbol), size, price, entry_datetime))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"ポジション保存エラー: {e}")

    def load_positions(self):
        \"\"\"すべてのポジション情報を辞書として読み込みます。\"\"\"
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
        \"\"\"指定された銘柄のポジション情報を削除します。\"\"\"
        sql = "DELETE FROM positions WHERE symbol = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (str(symbol),))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"ポジション削除エラー: {e}")

    def save_order(self, order_id, symbol, order_type, size, price, status):
        \"\"\"注文情報を保存または更新します。\"\"\"
        sql = "INSERT OR REPLACE INTO orders (order_id, symbol, order_type, size, price, status) VALUES (?, ?, ?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (order_id, str(symbol), order_type, size, price, status))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"注文保存エラー: {e}")

    def update_order_status(self, order_id, status):
        \"\"\"特定の注文のステータスを更新します。\"\"\"
        sql = "UPDATE orders SET status = ? WHERE order_id = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (status, order_id))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"注文ステータス更新エラー: {e}")
            
    def load_orders(self):
        \"\"\"すべての注文情報を辞書として読み込みます。\"\"\"
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
""",
    # --- モック実装とインターフェースファイルは変更なし ---
    "realtrade/mock/__init__.py": """# モック実装用のパッケージ""",
    "realtrade/mock/broker.py": """from realtrade.broker_bridge import BrokerBridge, OrderStatus
import logging

class MockBrokerBridge(BrokerBridge):
    def start(self): print("MockBroker: 接続しました。")
    def stop(self): print("MockBroker: 接続を終了しました。")
    def get_cash(self): return 10000000.0
    def get_position(self, data, clone=True): return 0.0
    def place_order(self, order):
        print(f"MockBroker: 注文リクエスト受信: {order.info}")
        order.executed.price = order.price
        order.executed.size = order.size
        self.notify(order)
    def cancel_order(self, order):
        print(f"MockBroker: 注文キャンセルリクエスト受信: {order.ref}")
        self.notify(order)
    def poll_orders(self): pass
""",
    "realtrade/mock/data_fetcher.py": """from realtrade.data_fetcher import DataFetcher, RealtimeDataFeed
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

class MockDataFetcher(DataFetcher):
    def start(self): print("MockDataFetcher: 起動しました。")
    def stop(self): print("MockDataFetcher: 停止しました。")
    def get_data_feed(self, symbol):
        if self.data_feeds.get(symbol) is None:
            df = self.fetch_historical_data(symbol, 'minutes', 1, 100)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]
    def fetch_historical_data(self, symbol, timeframe, compression, period):
        print(f"MockDataFetcher: 履歴データリクエスト受信 - 銘柄:{symbol}, 期間:{period}本")
        end_date = datetime.now()
        dates = pd.date_range(end=end_date, periods=period, freq=f'{compression}min')
        start_price = np.random.uniform(1000, 5000)
        prices = start_price * (1 + np.random.normal(loc=0, scale=0.01, size=period)).cumprod()
        data = {'open': prices, 'high': prices * 1.02, 'low': prices * 0.98, 'close': prices * 1.01, 'volume': np.random.randint(100, 10000, size=period)}
        df = pd.DataFrame(data, index=dates)
        df.columns = [col.lower() for col in df.columns]
        df['open'] = df['close'].shift(1); df.loc[df.index[0], 'open'] = start_price
        df['high'] = df[['open', 'close']].max(axis=1) * 1.01; df['low'] = df[['open', 'close']].min(axis=1) * 0.99
        return df
""",
    "realtrade/broker_bridge.py": """import backtrader as bt
from enum import Enum

class OrderStatus(Enum):
    SUBMITTED = 'submitted'; ACCEPTED = 'accepted'; PARTIALLY_FILLED = 'partially_filled'; FILLED = 'filled'; CANCELED = 'canceled'; REJECTED = 'rejected'; EXPIRED = 'expired'

class BrokerBridge(bt.broker.BrokerBase):
    def __init__(self, config):
        super(BrokerBridge, self).__init__(); self.config = config; self.positions = {}
    def start(self): raise NotImplementedError
    def stop(self): raise NotImplementedError
    def get_cash(self): raise NotImplementedError
    def get_position(self, data, clone=True): raise NotImplementedError
    def place_order(self, order): raise NotImplementedError
    def cancel_order(self, order): raise NotImplementedError
    def poll_orders(self): raise NotImplementedError
""",
    "realtrade/data_fetcher.py": """import backtrader as bt
import abc

class RealtimeDataFeed(bt.feeds.PandasData):
    def push_data(self, data_dict): pass

class DataFetcher(metaclass=abc.ABCMeta):
    def __init__(self, symbols, config):
        self.symbols = symbols; self.config = config; self.data_feeds = {s: None for s in symbols}
    @abc.abstractmethod
    def start(self): raise NotImplementedError
    @abc.abstractmethod
    def stop(self): raise NotImplementedError
    @abc.abstractmethod
    def get_data_feed(self, symbol): raise NotImplementedError
    @abc.abstractmethod
    def fetch_historical_data(self, symbol, timeframe, compression, period): raise NotImplementedError
"""
}

def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"ファイルを作成/更新しました: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("リアルタイムトレード用の【新規プロジェクトファイル】生成を開始します...")
    create_files(project_files_realtime)
    print("\\nリアルタイムトレード用の【新規プロジェクトファイル】の生成が完了しました。")
    print("\\n【重要】別途、既存ファイル('requirements.txt', 'btrader_strategy.py')の修正が必要です。")

