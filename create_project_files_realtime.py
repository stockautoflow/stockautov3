# ==============================================================================
# ファイル: create_project_files_realtime.py
# 説明: このスクリプトは、リアルタイム自動トレードシステムに
#       必要な「新規」ファイルとディレクトリの骨格のみを生成します。
#       既存ファイルは変更しません。
# バージョン: v4.0
# 主な変更点:
#   - realtrade/broker_bridge.py: BrokerBridgeインターフェースを詳細化
#   - realtrade/data_fetcher.py: DataFetcherインターフェースを詳細化
# ==============================================================================
import os

project_files_realtime = {
    # --- ▼▼▼ リアルタイムシステム用の新規ファイル ▼▼▼ ---

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
from datetime import datetime
import os
from dotenv import load_dotenv

# --- .envファイルから環境変数をロード ---
load_dotenv()

import config_realtrade as config
# import logger_setup
# ... (他のimportは後続ステップで有効化)

# logger_setup.setup_logging()
# logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        print("リアルタイムトレーダーを初期化中...")
        if not config.API_KEY or not config.API_SECRET:
            print("エラー: APIキーまたはシークレットが設定されていません。")
            raise ValueError("APIキーが設定されていません。")
        self.is_running = False

    def start(self):
        print("システムを開始します。")
        self.is_running = True
        pass

    def stop(self):
        print("システムを停止します。")
        self.is_running = False
        print("システムが正常に停止しました。")

if __name__ == '__main__':
    print("--- リアルタイムトレードシステム起動 ---")
    trader = RealtimeTrader()
    try:
        trader.start()
        print("システムは起動状態です。Ctrl+Cで終了します。")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\\nCtrl+Cを検知しました。システムを安全に停止します...")
        trader.stop()
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
        trader.stop()
""",

    "realtrade/__init__.py": """# このファイルは'realtrade'ディレクトリをPythonパッケージとして認識させるためのものです。
""",

    "realtrade/broker_bridge.py": """import backtrader as bt
import abc
from enum import Enum

# 注文状態の管理をしやすくするためのEnum
class OrderStatus(Enum):
    SUBMITTED = 'submitted'
    ACCEPTED = 'accepted'
    PARTIALLY_FILLED = 'partially_filled'
    FILLED = 'filled'
    CANCELED = 'canceled'
    REJECTED = 'rejected'
    EXPIRED = 'expired'

class BrokerBridge(bt.broker.BrokerBase, metaclass=abc.ABCMeta):
    \"\"\"
    証券会社APIと連携するためのインターフェース（抽象基底クラス）。
    このクラスを継承して、各証券会社専用のブリッジを実装します。
    \"\"\"
    def __init__(self, config):
        super(BrokerBridge, self).__init__()
        self.config = config
        self.positions = {} # ポジション情報を保持する辞書

    @abc.abstractmethod
    def start(self):
        \"\"\"ブローカーへの接続や初期化処理を行います。\"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        \"\"\"ブローカーとの接続を安全に終了します。\"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def get_cash(self):
        \"\"\"利用可能な現金額を取得します。\"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def get_position(self, data, clone=True):
        \"\"\"指定された銘柄のポジションサイズを取得します。\"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def place_order(self, order):
        \"\"\"
        backtraderから渡された注文オブジェクトを処理し、
        証券会社APIに発注リクエストを送信します。
        \"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def cancel_order(self, order):
        \"\"\"注文のキャンセルリクエストを送信します。\"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def poll_orders(self):
        \"\"\"
        未約定の注文の状態をAPIで確認し、変更があればbacktraderに
        通知 (notify_order) するためのロジックを実装します。
        メインループから定期的に呼び出されることを想定します。
        \"\"\"
        raise NotImplementedError
""",

    "realtrade/data_fetcher.py": """import backtrader as bt
import abc

class RealtimeDataFeed(bt.feeds.PandasData):
    \"\"\"
    リアルタイムデータをbacktraderに供給するためのカスタムデータフィード。
    PandasDataを継承し、新しいデータを動的に追加する機能を持つ。
    \"\"\"
    def push_data(self, data_dict):
        \"\"\"
        新しいローソク足データをフィードに追加します。
        :param data_dict: {'datetime': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}
        \"\"\"
        # このメソッドは、backtraderの内部構造にアクセスするため、
        # 慎重な実装が必要です。
        # 簡単な例として、新しい行を追加する処理を想定しますが、
        # 実際にはより複雑なハンドリングが必要になる場合があります。
        pass

class DataFetcher(metaclass=abc.ABCMeta):
    \"\"\"
    証券会社APIから価格データを取得するためのインターフェース（抽象基底クラス）。
    このクラスを継承して、各証券会社専用のデータ取得クラスを実装します。
    \"\"\"
    def __init__(self, symbols, config):
        \"\"\"
        :param symbols: 取得対象の銘柄コードのリスト
        :param config: 設定オブジェクト
        \"\"\"
        self.symbols = symbols
        self.config = config
        self.data_feeds = {s: None for s in symbols} # 銘柄ごとのデータフィードを保持

    @abc.abstractmethod
    def start(self):
        \"\"\"
        データ取得を開始します。
        (例: WebSocketへの接続、ポーリングスレッドの開始など)
        \"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        \"\"\"データ取得を安全に停止します。\"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def get_data_feed(self, symbol):
        \"\"\"
        指定された銘柄のデータフィードオブジェクトを返します。
        まだ生成されていない場合は、ここで生成します。
        :param symbol: 銘柄コード
        :return: RealtimeDataFeed のインスタンス
        \"\"\"
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_historical_data(self, symbol, timeframe, compression, period):
        \"\"\"
        戦略のインジケーター計算に必要な過去のデータを取得します。
        :param symbol: 銘柄コード
        :param timeframe: 'days', 'minutes'など
        :param compression: 1, 5, 60など
        :param period: 取得する期間の長さ (例: 100本)
        :return: pandas.DataFrame
        \"\"\"
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
                price REAL NOT NULL, entry_datetime TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
                order_type TEXT NOT NULL, size REAL NOT NULL,
                price REAL, status TEXT NOT NULL
            )
        ''')
        self.conn.commit()
        print("データベーステーブルの初期化を確認しました。")

    def close(self):
        if self.conn:
            self.conn.close()
            print("データベース接続をクローズしました。")
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
