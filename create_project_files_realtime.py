# ==============================================================================
# ファイル: create_project_files_realtime.py
# 説明: このスクリプトは、リアルタイム自動トレードシステムに
#       必要な「新規」ファイルとディレクトリの骨格のみを生成します。
# バージョン: v14.1 (最終修正版)
# 主な変更点:
#   - realtrade/analyzer.py: backtraderの仕様に基づき、`params`を
#     正しく定義。これにより、`__init__`での引数エラーを解決。
# ==============================================================================
import os

project_files_realtime = {
    # --- ▼▼▼ 新規ファイル ▼▼▼ ---

    ".env.example": """# このファイルをコピーして .env という名前のファイルを作成し、
# 実際のAPIキーに書き換えてください。
# .env ファイルは .gitignore に追加し、バージョン管理に含めないでください。

API_KEY="YOUR_API_KEY_HERE"
API_SECRET="YOUR_API_SECRET_HERE"
""",

    "config_realtrade.py": """import os
import logging

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
    print("警告: 環境変数 'API_KEY' が設定されていません。")
if not API_SECRET or API_SECRET == "YOUR_API_SECRET_HERE":
    print("警告: 環境変数 'API_SECRET' が設定されていません。")

RECOMMEND_FILE_PATTERN = "all_recommend_*.csv"
MAX_ORDER_SIZE_JPY = 1000000
MAX_CONCURRENT_ORDERS = 5
EMERGENCY_STOP_THRESHOLD = -0.1

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "realtrade", "db", "realtrade_state.db")

LOG_LEVEL = logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')

print("設定ファイルをロードしました (config_realtrade.py)")
""",

    "logger_setup.py": """import logging
import os
from datetime import datetime

def setup_logging(config_module, log_prefix):
    \"\"\"
    バックテストとリアルタイムトレードで共用できる汎用ロガーをセットアップします。
    
    :param config_module: 'config_backtrader' または 'config_realtrade' モジュール
    :param log_prefix: 'backtest' または 'realtime'
    \"\"\"
    log_dir = config_module.LOG_DIR
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    if log_prefix == 'backtest':
        log_filename = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"
    else:
        log_filename = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d')}.log"
    log_filepath = os.path.join(log_dir, log_filename)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=config_module.LOG_LEVEL,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, encoding='utf-8'),
                                  logging.StreamHandler()])
    print(f"ロガーをセットアップしました。モード: {log_prefix}, ログファイル: {log_filepath}")
""",

    "run_realtrade.py": """import logging
import time
import yaml
import pandas as pd
import glob
import os
from dotenv import load_dotenv
import backtrader as bt

load_dotenv()

import config_realtrade as config
import logger_setup
import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.mock.data_fetcher import MockDataFetcher
from realtrade.analyzer import TradePersistenceAnalyzer

logger_setup.setup_logging(config, log_prefix='realtime')
logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        if not config.API_KEY or not config.API_SECRET:
            logger.error("APIキーまたはシークレットが設定されていません。")
            raise ValueError("APIキーが設定されていません。")
        self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        logger.info(f"ロードした戦略カタログ: {list(self.strategy_catalog.keys())}")
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        logger.info(f"ロードした銘柄・戦略の割り当て: {self.strategy_assignments}")
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(config.DB_PATH)
        
        self.data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
        self.cerebro = self._setup_cerebro()
        self.is_running = False

    def _load_strategy_catalog(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return {s['name']: s for s in yaml.safe_load(f)}
        except FileNotFoundError:
            logger.error(f"戦略カタログファイル '{filepath}' が見つかりません。")
            raise

    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files:
            raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"最新の対応ファイルをロード: {latest_file}")
        df = pd.read_csv(latest_file)
        strategy_col, symbol_col = df.columns[0], df.columns[1]
        logger.info(f"CSVから読み込んだ列: 戦略='{strategy_col}', 銘柄='{symbol_col}'")
        return pd.Series(df[strategy_col].values, index=df[symbol_col].astype(str)).to_dict()

    def _setup_cerebro(self):
        logger.info("Cerebroエンジンをセットアップ中...")
        cerebro = bt.Cerebro(runonce=False)
        
        broker = bt.brokers.BackBroker()
        cerebro.setbroker(broker)
        logger.info("-> 標準のBackBrokerをセットしました。")

        for symbol in self.symbols:
            data_feed = self.data_fetcher.get_data_feed(str(symbol))
            if data_feed is not None:
                cerebro.adddata(data_feed, name=str(symbol))
            else:
                logger.warning(f"銘柄 {symbol} のデータフィードを取得できませんでした。スキップします。")
        
        logger.info(f"-> {len(self.symbols)}銘柄のデータフィードをCerebroに追加しました。")
        
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        logger.info("-> 永続化用AnalyzerをCerebroに追加しました。")

        cerebro.addstrategy(btrader_strategy.DynamicStrategy,
                            strategy_catalog=self.strategy_catalog,
                            strategy_assignments=self.strategy_assignments)
        logger.info("-> DynamicStrategyをCerebroに追加しました。")
        logger.info("Cerebroエンジンのセットアップが完了しました。")
        return cerebro

    def start(self):
        logger.info("システムを開始します。")
        self.data_fetcher.start()
        logger.info("ドライランを開始します... (実際の注文は行われません)")
        self.is_running = True
        self.cerebro.run()
        logger.info("ドライランが完了しました。")
        self.is_running = False

    def stop(self):
        logger.info("システムを停止します。")
        self.is_running = False
        if hasattr(self, 'data_fetcher'): self.data_fetcher.stop()
        if hasattr(self, 'state_manager'): self.state_manager.close()
        logger.info("システムが正常に停止しました。")

if __name__ == '__main__':
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
    except KeyboardInterrupt:
        logger.info("\\nCtrl+Cを検知しました。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
    logger.info("--- リアルタイムトレードシステム終了 ---")
""",
    # --- 他のファイルは変更なし、または修正対象ファイル ---
    "realtrade/__init__.py": """# このファイルは'realtrade'ディレクトリをPythonパッケージとして認識させるためのものです。
""",
    "realtrade/data_fetcher.py": """import backtrader as bt
import abc
import pandas as pd
from datetime import datetime, timedelta

class RealtimeDataFeed(bt.feeds.PandasData):
    pass

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
""",
    "realtrade/state_manager.py": """import sqlite3
import logging
import os

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self._create_tables()
            logger.info(f"データベースに接続しました: {db_path}")
        except sqlite3.Error as e:
            logger.critical(f"データベース接続エラー: {e}")
            raise

    def _create_tables(self):
        try:
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
                    status TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.conn.commit()
            logger.info("データベーステーブルの初期化を確認しました。")
        except sqlite3.Error as e:
            logger.error(f"テーブル作成エラー: {e}")

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("データベース接続をクローズしました。")

    def save_position(self, symbol, size, price, entry_datetime):
        sql = "INSERT OR REPLACE INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (str(symbol), size, price, entry_datetime))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"ポジション保存エラー: {e}")

    def load_positions(self):
        positions = {}
        sql = "SELECT symbol, size, price, entry_datetime FROM positions"
        try:
            cursor = self.conn.cursor()
            for row in cursor.execute(sql):
                positions[row[0]] = {'size': row[1], 'price': row[2], 'entry_datetime': row[3]}
            logger.info(f"{len(positions)}件のポジションをDBからロードしました。")
            return positions
        except sqlite3.Error as e:
            logger.error(f"ポジション読み込みエラー: {e}")
            return {}

    def delete_position(self, symbol):
        sql = "DELETE FROM positions WHERE symbol = ?"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (str(symbol),))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"ポジション削除エラー: {e}")

    def save_order(self, order_id, symbol, order_type, size, price, status):
        sql = "INSERT OR REPLACE INTO orders (order_id, symbol, order_type, size, price, status) VALUES (?, ?, ?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, (order_id, str(symbol), order_type, size, price, status))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"注文保存エラー: {e}")

    def load_orders(self):
        orders = {}
        sql = "SELECT order_id, symbol, order_type, size, price, status FROM orders"
        try:
            cursor = self.conn.cursor()
            for row in cursor.execute(sql):
                orders[row[0]] = {'symbol': row[1], 'order_type': row[2], 'size': row[3], 'price': row[4], 'status': row[5]}
            return orders
        except sqlite3.Error as e:
            logger.error(f"注文読み込みエラー: {e}")
            return {}
""",
    # [修正] Analyzerのパラメータ定義を修正
    "realtrade/analyzer.py": """import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class TradePersistenceAnalyzer(bt.Analyzer):
    \"\"\"
    取引イベントをフックし、ポジションの状態をデータベースに永続化するAnalyzer。
    \"\"\"
    params = (
        ('state_manager', None),
    )
    
    def __init__(self):
        if not self.p.state_manager:
            raise ValueError("StateManagerがAnalyzerに渡されていません。")
        self.state_manager = self.p.state_manager
        logger.info("TradePersistenceAnalyzer initialized.")

    def notify_trade(self, trade):
        \"\"\"
        取引の発生（オープン・クローズ）を通知されるメソッド。
        \"\"\"
        super().notify_trade(trade)

        # Cerebroエンジンは、ストラテジーのインスタンスには `self.strategy` でアクセス可能
        pos = self.strategy.broker.getposition(trade.data)
        symbol = trade.data._name
        
        if trade.isopen:
            entry_dt = bt.num2date(trade.dtopen).isoformat()
            self.state_manager.save_position(symbol, pos.size, pos.price, entry_dt)
            logger.info(f"StateManager: ポジションをDBに保存/更新しました: {symbol} (New Size: {pos.size})")
        
        if trade.isclosed:
            self.state_manager.delete_position(symbol)
            logger.info(f"StateManager: ポジションをDBから削除しました: {symbol}")
""",
    "realtrade/mock/__init__.py": """# モック実装用のパッケージ
""",
    "realtrade/mock/data_fetcher.py": """from realtrade.data_fetcher import DataFetcher, RealtimeDataFeed
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MockDataFetcher(DataFetcher):
    def start(self):
        logger.info("MockDataFetcher: 起動しました。")

    def stop(self):
        logger.info("MockDataFetcher: 停止しました。")

    def get_data_feed(self, symbol):
        if self.data_feeds.get(symbol) is None:
            df = self.fetch_historical_data(symbol, 'minutes', 1, 200)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]

    def fetch_historical_data(self, symbol, timeframe, compression, period):
        logger.info(f"MockDataFetcher: 履歴データリクエスト受信 - 銘柄:{symbol}, 期間:{period}本")
        end_date = datetime.now()
        dates = pd.date_range(end=end_date, periods=period, freq=f'{compression}min').tz_localize(None)
        
        start_price = np.random.uniform(1000, 5000)
        returns = np.random.normal(loc=0.0001, scale=0.01, size=period)
        prices = start_price * (1 + returns).cumprod()
        
        df = pd.DataFrame(index=dates)
        df['open'] = prices
        df['high'] = prices * (1 + np.random.uniform(0, 0.01, size=period))
        df['low'] = prices * (1 - np.random.uniform(0, 0.01, size=period))
        df['close'] = prices * (1 + np.random.normal(loc=0, scale=0.005, size=period))
        
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.005, size=period))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.005, size=period))
        
        df['volume'] = np.random.randint(100, 10000, size=period)
        df.columns = [col.lower() for col in df.columns]
        
        return df
"""
}

def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
    files_to_remove = ["realtrade/mock/broker.py", "realtrade/broker_bridge.py"]
    for f in files_to_remove:
        if f in files_dict:
            del files_dict[f]
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"古いファイルを削除しました: {f}")
            except OSError as e:
                print(f"古いファイルの削除に失敗しました: {e}")

    for filename, content in files_dict.items():
        if not content or content.strip() == "":
            continue
            
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
    print("\\n【重要】次の手順で動作確認を行ってください:")
    print("1. このスクリプト(`create_project_files_realtime.py`)を実行して、最新のファイルを生成します。")
    print("2. `run_realtrade.py` を実行します。")
    print("3. エラーが出ずに正常に終了し、ログに `StateManager: ポジションをDBに保存しました` 等のメッセージが出力されることを確認します。")
    print("4. 実行後、`realtrade/db/realtrade_state.db` というファイルが生成・更新されていることを確認します。")

