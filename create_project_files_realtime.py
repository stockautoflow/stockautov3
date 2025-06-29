# ==============================================================================
# ファイル: create_project_files_realtime.py
# 説明: このスクリプトは、リアルタイム自動トレードシステムに
#       必要なファイルとディレクトリの骨格を生成します。
# バージョン: v15.0
# 主な変更点:
#   - ライブトレーディング機能の追加
#     - `config_realtrade.py`にLIVE_TRADINGフラグを追加。
#     - `run_realtrade.py`をライブ/モックモードの切り替えに対応。
#     - `realtrade/live`パッケージを新設し、実際のAPI連携用の
#       Store, Broker, Dataの骨格 (sbi_*.py) を追加。
# ==============================================================================
import os

project_files_realtime = {
    # --- ▼▼▼ 設定ファイル ▼▼▼ ---
    ".env.example": """# このファイルをコピーして .env という名前のファイルを作成し、
# 実際のAPIキーに書き換えてください。
# .env ファイルは .gitignore に追加し、バージョン管理に含めないでください。

# --- 証券会社API ---
API_KEY="YOUR_API_KEY_HERE"
API_SECRET="YOUR_API_SECRET_HERE"

# --- [任意] 通知用 (未実装) ---
LINE_NOTIFY_TOKEN="YOUR_LINE_NOTIFY_TOKEN_HERE"
""",

    "config_realtrade.py": """import os
import logging

# ==============================================================================
# --- グローバル設定 ---
# ==============================================================================
# Trueにすると実際の証券会社APIに接続します。
# FalseにするとMockDataFetcherを使用し、シミュレーションを実行します。
LIVE_TRADING = False

# --- API認証情報 (環境変数からロード) ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

if LIVE_TRADING:
    print("<<< ライブトレーディングモードで起動します >>>")
    if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
        raise ValueError("環境変数 'API_KEY' が設定されていません。")
    if not API_SECRET or API_SECRET == "YOUR_API_SECRET_HERE":
        raise ValueError("環境変数 'API_SECRET' が設定されていません。")
else:
    print("<<< シミュレーションモードで起動します (MockDataFetcher使用) >>>")


# ==============================================================================
# --- 取引設定 ---
# ==============================================================================
# 1注文あたりの最大投資額（日本円）
MAX_ORDER_SIZE_JPY = 1000000

# 同時に発注できる最大注文数
MAX_CONCURRENT_ORDERS = 5

# 緊急停止する資産減少率の閾値 (例: -0.1は資産が10%減少したら停止)
EMERGENCY_STOP_THRESHOLD = -0.1

# 取引対象の銘柄と戦略が書かれたファイル名のパターン
RECOMMEND_FILE_PATTERN = "all_recommend_*.csv"


# ==============================================================================
# --- システム設定 ---
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- データベース ---
DB_PATH = os.path.join(BASE_DIR, "realtrade", "db", "realtrade_state.db")

# --- ロギング ---
LOG_LEVEL = logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')

print("設定ファイルをロードしました (config_realtrade.py)")
""",

    # --- ▼▼▼ メイン実行スクリプト ▼▼▼ ---
    "run_realtrade.py": """import logging
import time
import yaml
import pandas as pd
import glob
import os
from dotenv import load_dotenv
import backtrader as bt

# 環境変数をロード
load_dotenv()

# モジュールをインポート
import config_realtrade as config
import logger_setup
import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.analyzer import TradePersistenceAnalyzer

# --- モードに応じてインポートするモジュールを切り替え ---
if config.LIVE_TRADING:
    from realtrade.live.sbi_store import SBIStore
    from realtrade.live.sbi_broker import SBIBroker
    from realtrade.live.sbi_data import SBIData
else:
    from realtrade.mock.data_fetcher import MockDataFetcher

# ロガーのセットアップ
logger_setup.setup_logging(config, log_prefix='realtime')
logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(config.DB_PATH)
        
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
        return pd.Series(df[strategy_col].values, index=df[symbol_col].astype(str)).to_dict()

    def _setup_cerebro(self):
        logger.info("Cerebroエンジンをセットアップ中...")
        cerebro = bt.Cerebro(runonce=False) # リアルタイムなのでrunonce=False
        
        # --- Live/Mockモードに応じてBrokerとDataFeedを設定 ---
        if config.LIVE_TRADING:
            logger.info("ライブモード用のStore, Broker, DataFeedをセットアップします。")
            store = SBIStore(
                api_key=config.API_KEY,
                api_secret=config.API_SECRET
            )
            
            # Brokerをセット
            broker = SBIBroker(store=store)
            cerebro.setbroker(broker)
            logger.info("-> SBIBrokerをCerebroにセットしました。")
            
            # データフィードをセット
            for symbol in self.symbols:
                data_feed = SBIData(dataname=symbol, store=store)
                cerebro.adddata(data_feed, name=str(symbol))
            logger.info(f"-> {len(self.symbols)}銘柄のSBIDataフィードをCerebroに追加しました。")
            
        else: # シミュレーションモード
            logger.info("シミュレーションモード用のBrokerとDataFeedをセットアップします。")
            data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
            
            # Brokerをセット (標準のBackBroker)
            broker = bt.brokers.BackBroker()
            cerebro.setbroker(broker)
            logger.info("-> 標準のBackBrokerをセットしました。")
            
            # データフィードをセット
            for symbol in self.symbols:
                data_feed = data_fetcher.get_data_feed(str(symbol))
                cerebro.adddata(data_feed, name=str(symbol))
            logger.info(f"-> {len(self.symbols)}銘柄のMockデータフィードをCerebroに追加しました。")
        
        # --- 共通のセットアップ ---
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
        self.is_running = True
        self.cerebro.run()
        logger.info("Cerebroの実行が完了しました。")
        self.is_running = False

    def stop(self):
        logger.info("システムを停止します。")
        self.is_running = False
        if self.state_manager:
            self.state_manager.close()
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
    # --- ▼▼▼ ライブ取引用の新規ファイル ▼▼▼ ---
    "realtrade/live/__init__.py": """# このディレクトリは、実際の証券会社APIと連携するためのモジュールを含みます。
""",
    "realtrade/live/sbi_store.py": """import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class SBIStore(bt.stores.Store):
    \"\"\"
    証券会社のAPIとの通信を管理するクラス。
    認証、残高取得、注文、データ取得などの窓口となる。
    \"\"\"
    def __init__(self, api_key, api_secret, paper_trading=True):
        super(SBIStore, self).__init__()
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper_trading = paper_trading
        
        # ここでAPIクライアントの初期化を行う (例: requests.Session)
        # self.api_client = self._create_api_client()
        
        logger.info(f"SBIStoreを初期化しました。ペーパートレード: {self.paper_trading}")

    def _create_api_client(self):
        \"\"\"APIクライアントを生成し、認証を行う\"\"\"
        # (ここに実際のAPI認証ロジックを実装)
        logger.info("APIクライアントの認証を実行します...")
        # 認証成功
        # logger.info("API認証成功")
        # return client
        pass

    def get_cash(self):
        \"\"\"利用可能な現金を返す\"\"\"
        logger.debug("APIから現金残高を取得しています...")
        # (ここに実際のAPI呼び出しを実装)
        # return cash_balance
        return 10000000 # ダミーの値を返す

    def get_value(self):
        \"\"\"資産の現在価値を返す\"\"\"
        logger.debug("APIから資産価値を取得しています...")
        # (ここに実際のAPI呼び出しを実装)
        # return asset_value
        return 10000000 # ダミーの値を返す

    def get_positions(self):
        \"\"\"現在のポジション一覧を返す\"\"\"
        logger.debug("APIからポジション一覧を取得しています...")
        # (ここに実際のAPI呼び出しを実装)
        # return positions
        return [] # ダミーの値を返す
    
    def place_order(self, order):
        \"\"\"注文をAPIに送信する\"\"\"
        logger.info(f"【API連携】注文を送信します: {order}")
        # (ここに実際の注文送信ロジックを実装)
        # is_buy = order.isbuy()
        # symbol = order.data._name
        # size = order.size
        # ...
        logger.info("注文がAPIに正常に送信されました (仮)")
        # 戻り値として、APIから返された注文IDなどを返す
        return f"api-order-{id(order)}"
        
    def cancel_order(self, order_id):
        \"\"\"注文のキャンセルをAPIに送信する\"\"\"
        logger.info(f"【API連携】注文キャンセルを送信します: OrderID={order_id}")
        # (ここに実際の注文キャンセルロジックを実装)
        pass

    def get_historical_data(self, dataname, timeframe, compression, period):
        \"\"\"履歴データを取得する\"\"\"
        logger.info(f"【API連携】履歴データを取得します: {dataname} ({period}本)")
        # (ここに実際の履歴データ取得ロジックを実装)
        # ...
        # return pandas_dataframe
        return None # SBIDataで直接実装するため、ここではNoneを返す

    def get_streaming_data(self, dataname):
        \"\"\"リアルタイムデータ (ストリーミング) を取得する\"\"\"
        # (ストリーミングAPIを使用する場合、ここで接続を開始する)
        logger.info(f"【API連携】ストリーミングデータを要求します: {dataname}")
        # return data_queue
        pass
""",
    "realtrade/live/sbi_broker.py": """import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class SBIBroker(bt.brokers.BrokerBase):
    \"\"\"
    backtraderのBrokerとして振る舞い、SBIStore経由で実際の取引を行う。
    \"\"\"
    def __init__(self, store):
        super(SBIBroker, self).__init__()
        self.store = store
        self.orders = [] # 未約定の注文を管理
        logger.info("SBIBrokerを初期化しました。")

    def start(self):
        super(SBIBroker, self).start()
        self.cash = self.store.get_cash()
        self.value = self.store.get_value()
        logger.info(f"Brokerを開始しました。現金: {self.cash}, 資産価値: {self.value}")

    def buy(self, owner, data, size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0, oco=None,
            trailamount=None, trailpercent=None, **kwargs):
        
        order = super().buy(owner, data, size, price, plimit,
                            exectype, valid, tradeid, oco,
                            trailamount, trailpercent, **kwargs)
        # 実際のAPIに注文を送信
        api_order_id = self.store.place_order(order)
        order.api_id = api_order_id # APIの注文IDを保存
        self.orders.append(order)
        self.notify(order)
        return order

    def sell(self, owner, data, size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0, oco=None,
             trailamount=None, trailpercent=None, **kwargs):

        order = super().sell(owner, data, size, price, plimit,
                             exectype, valid, tradeid, oco,
                             trailamount, trailpercent, **kwargs)
        # 実際のAPIに注文を送信
        api_order_id = self.store.place_order(order)
        order.api_id = api_order_id # APIの注文IDを保存
        self.orders.append(order)
        self.notify(order)
        return order

    def cancel(self, order):
        if order.status == bt.Order.Submitted or order.status == bt.Order.Accepted:
            self.store.cancel_order(order.api_id)
            order.cancel()
            self.notify(order)
        return order
""",
    "realtrade/live/sbi_data.py": """import backtrader as bt
import pandas as pd
from datetime import datetime
import time
import threading
import random
import logging

logger = logging.getLogger(__name__)

class SBIData(bt.feeds.PandasData):
    \"\"\"
    SBIStore経由でリアルタイムデータを取得し、Cerebroに供給するデータフィード。
    \"\"\"
    params = (
        ('store', None),
        ('timeframe', bt.TimeFrame.Minutes),
        ('compression', 1),
    )

    def __init__(self, **kwargs):
        super(SBIData, self).__init__(**kwargs)
        if not self.p.store:
            raise ValueError("SBIDataにはstoreの指定が必要です。")
        self.store = self.p.store
        self._thread = None
        self._stop_event = threading.Event()
        
        # 履歴データを取得して初期化
        self.init_data = self.store.get_historical_data(
            self.p.dataname, self.p.timeframe, self.p.compression, 200
        )

    def start(self):
        super(SBIData, self).start()
        if self.init_data is not None and not self.init_data.empty:
            logger.info(f"[{self.p.dataname}] 履歴データをロードします。")
            self.add_history(self.init_data)
        
        logger.info(f"[{self.p.dataname}] リアルタイムデータ取得スレッドを開始します...")
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.p.dataname}] リアルタイムデータ取得スレッドを停止します...")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        super(SBIData, self).stop()

    def _run(self):
        \"\"\"バックグラウンドで価格データを生成/取得し続ける\"\"\"
        while not self._stop_event.is_set():
            try:
                # 本来はここでWebSocketやAPIポーリングを行う
                # --- ここから下はダミーデータ生成ロジック ---
                time.sleep(5) # 5秒ごとに更新をシミュレート
                
                # 直前の足のデータを取得
                last_close = self.close[-1] if len(self.close) > 0 else 1000
                
                # 新しい足のデータを生成
                new_open = self.open[0] = self.close[0] if len(self.open) > 0 else last_close
                change = random.uniform(-0.005, 0.005)
                new_close = new_open * (1 + change)
                new_high = max(new_open, new_close) * (1 + random.uniform(0, 0.002))
                new_low = min(new_open, new_close) * (1 - random.uniform(0, 0.002))
                new_volume = random.randint(100, 5000)

                # backtraderにデータをセット
                self.lines.datetime[0] = bt.date2num(datetime.now())
                self.lines.open[0] = new_open
                self.lines.high[0] = new_high
                self.lines.low[0] = new_low
                self.lines.close[0] = new_close
                self.lines.volume[0] = new_volume
                
                self.put_notification(self.LIVE) # データ更新をCerebroに通知
                # --- ダミーデータ生成ロジックここまで ---

            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}")
                time.sleep(10) # エラー発生時は少し待つ

    def add_history(self, df):
        \"\"\"履歴データをデータフィードにロードする\"\"\"
        if df is None or df.empty: return
        
        for index, row in df.iterrows():
            self.lines.datetime[0] = bt.date2num(index.to_pydatetime())
            self.lines.open[0] = row['open']
            self.lines.high[0] = row['high']
            self.lines.low[0] = row['low']
            self.lines.close[0] = row['close']
            self.lines.volume[0] = row['volume']
            self.put_notification(self.DELAYED)
""",

    # --- ▼▼▼ 既存ファイル (変更なし、または微修正) ▼▼▼ ---
    "realtrade/__init__.py": """# このファイルは'realtrade'ディレクトリをPythonパッケージとして認識させるためのものです。
""",
    "realtrade/data_fetcher.py": """# このファイルはシミュレーションモードでのみ使用されます。
# ライブトレーディングでは realtrade/live/sbi_data.py が使用されます。
import backtrader as bt
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
            self.conn.commit()
        except sqlite3.Error as e: logger.error(f"テーブル作成エラー: {e}")

    def close(self):
        if self.conn: self.conn.close(); logger.info("データベース接続をクローズしました。")

    def save_position(self, symbol, size, price, entry_datetime):
        sql = "INSERT OR REPLACE INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor(); cursor.execute(sql, (str(symbol), size, price, entry_datetime)); self.conn.commit()
        except sqlite3.Error as e: logger.error(f"ポジション保存エラー: {e}")

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
            logger.error(f"ポジション読み込みエラー: {e}"); return {}

    def delete_position(self, symbol):
        sql = "DELETE FROM positions WHERE symbol = ?"
        try:
            cursor = self.conn.cursor(); cursor.execute(sql, (str(symbol),)); self.conn.commit()
        except sqlite3.Error as e: logger.error(f"ポジション削除エラー: {e}")
""",
    "realtrade/analyzer.py": """import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class TradePersistenceAnalyzer(bt.Analyzer):
    params = (('state_manager', None),)
    
    def __init__(self):
        if not self.p.state_manager: raise ValueError("StateManagerがAnalyzerに渡されていません。")
        self.state_manager = self.p.state_manager
        logger.info("TradePersistenceAnalyzer initialized.")

    def notify_trade(self, trade):
        super().notify_trade(trade)
        pos, symbol = self.strategy.broker.getposition(trade.data), trade.data._name
        if trade.isopen:
            entry_dt = bt.num2date(trade.dtopen).isoformat()
            self.state_manager.save_position(symbol, pos.size, pos.price, entry_dt)
            logger.info(f"StateManager: ポジションをDBに保存/更新: {symbol} (New Size: {pos.size})")
        if trade.isclosed:
            self.state_manager.delete_position(symbol)
            logger.info(f"StateManager: ポジションをDBから削除: {symbol}")
""",
    "realtrade/mock/__init__.py": """# シミュレーションモード用のモック実装パッケージ
""",
    "realtrade/mock/data_fetcher.py": """from realtrade.data_fetcher import DataFetcher, RealtimeDataFeed
import pandas as pd
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MockDataFetcher(DataFetcher):
    def start(self): logger.info("MockDataFetcher: 起動しました。")
    def stop(self): logger.info("MockDataFetcher: 停止しました。")

    def get_data_feed(self, symbol):
        if self.data_feeds.get(symbol) is None:
            df = self._generate_dummy_data(symbol, 200)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]

    def _generate_dummy_data(self, symbol, period):
        logger.info(f"MockDataFetcher: ダミー履歴データ生成 - 銘柄:{symbol}, 期間:{period}本")
        dates = pd.date_range(end=datetime.now(), periods=period, freq='1min').tz_localize(None)
        start_price, prices = np.random.uniform(1000, 5000), []
        current_price = start_price
        for _ in range(period):
            current_price *= (1 + np.random.normal(loc=0.0001, scale=0.01))
            prices.append(current_price)
        
        df = pd.DataFrame(index=dates)
        df['open'] = prices
        df['close'] = [p * (1 + np.random.normal(0, 0.005)) for p in prices]
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.005, size=period))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.005, size=period))
        df['volume'] = np.random.randint(100, 10000, size=period)
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
        if not content: continue
        
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"ファイルを作成/更新しました: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("リアルタイムトレード用のプロジェクトファイル生成を開始します...")
    create_files(project_files_realtime)
    print("\nプロジェクトファイルの生成が完了しました。")
    print("\n【重要】次の手順で動作確認を行ってください:")
    print("1. このスクリプト(`create_project_files_realtime.py`)を実行して、最新のファイルを生成します。")
    print("2. (シミュレーション) `config_realtrade.py` の `LIVE_TRADING` が `False` であることを確認し、`run_realtrade.py` を実行します。")
    print("3. (ライブテスト) `.env`ファイルにAPIキーを設定し、`config_realtrade.py`の`LIVE_TRADING`を`True`に変更します。")
    print("4. (ライブテスト) `realtrade/live/` 内の各ファイルに、お使いの証券会社のAPI仕様に合わせた実装を追加します。")
    print("5. (ライブテスト) `run_realtrade.py` を実行し、実際のAPIと連携して動作することを確認します。")

