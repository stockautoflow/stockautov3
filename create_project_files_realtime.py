# ==============================================================================
# ファイル: create_project_files_realtime.py
# 説明: このスクリプトは、リアルタイム自動トレードシステムに
#       必要な「新規」ファイルとディレクトリの骨格のみを生成します。
#       既存ファイルは変更しません。
# バージョン: v5.2
# 主な変更点:
#   - realtrade/broker_bridge.py: メタクラスの競合エラーを修正
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
from realtrade.mock.broker import MockBrokerBridge # [変更] モックをインポート
from realtrade.mock.data_fetcher import MockDataFetcher # [変更] モックをインポート

# logger_setup.setup_logging()
# logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        print("リアルタイムトレーダーを初期化中...")
        if not config.API_KEY or not config.API_SECRET:
            print("エラー: APIキーまたはシークレットが設定されていません。")
            raise ValueError("APIキーが設定されていません。")

        # 戦略・銘柄リストの読み込み
        # self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        # self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        # symbols = list(self.strategy_assignments.keys())

        # モック用のダミー銘柄リスト
        symbols = [1301, 7203] 
        print(f"対象銘柄: {symbols}")

        # 各モジュールの初期化
        self.state_manager = StateManager(config.DB_PATH)
        self.broker = MockBrokerBridge(config=config)
        self.data_fetcher = MockDataFetcher(symbols=symbols, config=config)
        
        # self.cerebro = self._setup_cerebro()
        self.is_running = False

    def _load_strategy_catalog(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            strategies = yaml.safe_load(f)
        return {s['name']: s for s in strategies}

    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files:
            raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        df = pd.read_csv(latest_file)
        return pd.Series(df.strategy_name.values, index=df.symbol).to_dict()

    def start(self):
        print("システムを開始します。")
        self.broker.start()
        self.data_fetcher.start()

        # 動作確認: 現金残高を取得して表示
        cash = self.broker.get_cash()
        print(f"ブローカーから取得した現金残高: ¥{cash:,.0f}")
        
        # 動作確認: 履歴データを取得して表示
        hist_data = self.data_fetcher.fetch_historical_data(1301, 'minutes', 5, 10)
        print("データ取得モジュールから取得した履歴データ (先頭5行):")
        print(hist_data.head())

        self.is_running = True
        print("システムは起動状態です。Ctrl+Cで終了します。")


    def stop(self):
        print("システムを停止します。")
        self.broker.stop()
        self.data_fetcher.stop()
        self.state_manager.close()
        self.is_running = False
        print("システムが正常に停止しました。")

if __name__ == '__main__':
    print("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while True:
            # ここにメインループの処理（注文状態のポーリングなど）が入る
            time.sleep(1)
    except KeyboardInterrupt:
        print("\\nCtrl+Cを検知しました。システムを安全に停止します...")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
    finally:
        if trader:
            trader.stop()
""",

    "realtrade/__init__.py": """# このファイルは'realtrade'ディレクトリをPythonパッケージとして認識させるためのものです。
""",

    "realtrade/broker_bridge.py": """import backtrader as bt
from enum import Enum

class OrderStatus(Enum):
    SUBMITTED = 'submitted'
    ACCEPTED = 'accepted'
    PARTIALLY_FILLED = 'partially_filled'
    FILLED = 'filled'
    CANCELED = 'canceled'
    REJECTED = 'rejected'
    EXPIRED = 'expired'

class BrokerBridge(bt.broker.BrokerBase):
    \"\"\"
    証券会社APIと連携するためのインターフェース（基底クラス）。
    このクラスを継承して、各証券会社専用のブリッジを実装します。
    \"\"\"
    def __init__(self, config):
        super(BrokerBridge, self).__init__()
        self.config = config
        self.positions = {}

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def get_cash(self):
        raise NotImplementedError

    def get_position(self, data, clone=True):
        raise NotImplementedError

    def place_order(self, order):
        raise NotImplementedError

    def cancel_order(self, order):
        raise NotImplementedError

    def poll_orders(self):
        raise NotImplementedError
""",

    "realtrade/data_fetcher.py": """import backtrader as bt
import abc
import pandas as pd
from datetime import datetime, timedelta

class RealtimeDataFeed(bt.feeds.PandasData):
    def push_data(self, data_dict):
        # 現時点では未実装
        pass

class DataFetcher(metaclass=abc.ABCMeta):
    def __init__(self, symbols, config):
        self.symbols = symbols
        self.config = config
        self.data_feeds = {s: None for s in symbols}
    @abc.abstractmethod
    def start(self):
        raise NotImplementedError
    @abc.abstractmethod
    def stop(self):
        raise NotImplementedError
    @abc.abstractmethod
    def get_data_feed(self, symbol):
        raise NotImplementedError
    @abc.abstractmethod
    def fetch_historical_data(self, symbol, timeframe, compression, period):
        raise NotImplementedError
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
""",
    # --- ▼▼▼ [新規追加] モック実装 ▼▼▼ ---
    "realtrade/mock/__init__.py": """# モック実装用のパッケージ
""",
    "realtrade/mock/broker.py": """from realtrade.broker_bridge import BrokerBridge, OrderStatus
import logging

class MockBrokerBridge(BrokerBridge):
    \"\"\"
    実際のAPIに接続せず、ダミーデータを返す模擬ブローカー。
    システムの基本ロジックをテストするために使用します。
    \"\"\"
    def start(self):
        print("MockBroker: 接続しました。")

    def stop(self):
        print("MockBroker: 接続を終了しました。")

    def get_cash(self):
        # ダミーの現金額を返す
        return 10000000.0

    def get_position(self, data, clone=True):
        # 常にポジション0を返す
        return 0.0

    def place_order(self, order):
        print(f"MockBroker: 注文リクエスト受信: {order.info}")
        # 即座に約定したと仮定して通知
        order.executed.price = order.price
        order.executed.size = order.size
        self.notify(order)

    def cancel_order(self, order):
        print(f"MockBroker: 注文キャンセルリクエスト受信: {order.ref}")
        self.notify(order) # キャンセルを通知

    def poll_orders(self):
        # モックなので何もしない
        pass
""",

    "realtrade/mock/data_fetcher.py": """from realtrade.data_fetcher import DataFetcher, RealtimeDataFeed
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

class MockDataFetcher(DataFetcher):
    \"\"\"
    ダミーの価格データを生成して返す模擬データフェッチャー。
    \"\"\"
    def start(self):
        print("MockDataFetcher: 起動しました。")

    def stop(self):
        print("MockDataFetcher: 停止しました。")

    def get_data_feed(self, symbol):
        # ダミーのデータフィードを返す
        if self.data_feeds.get(symbol) is None:
            df = self.fetch_historical_data(symbol, 'minutes', 1, 100)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]

    def fetch_historical_data(self, symbol, timeframe, compression, period):
        \"\"\"ダミーのOHLCVデータをDataFrameで生成します。\"\"\"
        print(f"MockDataFetcher: 履歴データリクエスト受信 - 銘柄:{symbol}, 期間:{period}本")
        end_date = datetime.now()
        dates = pd.date_range(end=end_date, periods=period, freq=f'{compression}min')
        
        # ランダムウォークで価格データを生成
        start_price = np.random.uniform(1000, 5000)
        returns = np.random.normal(loc=0, scale=0.01, size=period)
        prices = start_price * (1 + returns).cumprod()

        data = {
            'open': prices,
            'high': prices * np.random.uniform(1, 1.02, size=period),
            'low': prices * np.random.uniform(0.98, 1, size=period),
            'close': prices * np.random.uniform(0.99, 1.01, size=period),
            'volume': np.random.randint(100, 10000, size=period)
        }
        df = pd.DataFrame(data, index=dates)
        # カラム名を小文字に統一
        df.columns = [col.lower() for col in df.columns]
        # open, high, low, closeを再計算して整合性を保つ
        df['open'] = df['close'].shift(1)
        df.loc[df.index[0], 'open'] = start_price
        df['high'] = df[['open', 'close']].max(axis=1) * 1.01
        df['low'] = df[['open', 'close']].min(axis=1) * 0.99

        return df
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
