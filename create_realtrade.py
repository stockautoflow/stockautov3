import os
import sys

# ==============================================================================
# ファイル: create_realtrade.py
# 説明: リファクタリング計画に基づき、リアルタイム取引機能を持つ`realtrade`パッケージを生成します。
#       このスクリプトは、リファクタリングのフェーズ3.1で一度だけ実行することを想定しています。
# 実行方法: python create_realtrade.py
# `python -m src.realtrade.run_realtrade
# Ver. 00-05
# ==============================================================================

realtrade_files = {
    # パッケージ初期化ファイル
    "src/realtrade/__init__.py": "",
    "src/realtrade/live/__init__.py": "",
    "src/realtrade/mock/__init__.py": "",

    # リアルタイム取引用の設定ファイル
    "src/realtrade/config_realtrade.py": """
import os
import logging
from dotenv import load_dotenv

# .envファイルから環境変数をロード
load_dotenv()

# --- プロジェクトルート設定 ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# ==============================================================================
# --- グローバル設定 ---
# ==============================================================================
# Trueにすると実際の証券会社APIやデータソースに接続します。
# FalseにするとMockDataFetcherを使用し、シミュレーションを実行します。
LIVE_TRADING = True

# ライブトレーディング時のデータソースを選択: 'SBI' または 'YAHOO'
# 'YAHOO' を選択した場合、売買機能はシミュレーション(BackBroker)になります。
DATA_SOURCE = 'YAHOO'

# --- API認証情報 (環境変数からロード) ---
# DATA_SOURCEが'SBI'の場合に利用されます
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

if LIVE_TRADING:
    print(f"<<< ライブモード ({DATA_SOURCE}) で起動します >>>")
    if DATA_SOURCE == 'SBI':
        if not API_KEY or "YOUR_API_KEY_HERE" in API_KEY:
            print("警告: 環境変数 'API_KEY' が設定されていません。")
        if not API_SECRET or "YOUR_API_SECRET_HERE" in API_SECRET:
            print("警告: 環境変数 'API_SECRET' が設定されていません。")
else:
    print("<<< シミュレーションモードで起動します (MockDataFetcher使用) >>>")

# ==============================================================================
# --- 取引設定 ---
# ==============================================================================
INITIAL_CAPITAL = 50000000000000

# 1注文あたりの最大投資額（日本円）
MAX_ORDER_SIZE_JPY = 1000000

# 同時に発注できる最大注文数
MAX_CONCURRENT_ORDERS = 5

# 緊急停止する資産減少率の閾値 (例: -0.1は資産が10%減少したら停止)
EMERGENCY_STOP_THRESHOLD = -0.1

# 取引対象の銘柄と戦略が書かれたファイル名のパターン
RECOMMEND_FILE_PATTERN = os.path.join(BASE_DIR, "results", "evaluation", "*", "all_recommend_*.csv")

# ==============================================================================
# --- システム設定 ---
# ==============================================================================
DB_PATH = os.path.join(BASE_DIR, "results", "realtrade", "realtrade_state.db")
LOG_LEVEL = logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')
""",

    # 状態管理モジュール
    "src/realtrade/state_manager.py": """
import sqlite3
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
""",

    # 取引永続化アナライザー
    "src/realtrade/analyzer.py": """
import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class TradePersistenceAnalyzer(bt.Analyzer):
    params = (('state_manager', None),)
    
    def __init__(self):
        if not self.p.state_manager:
            raise ValueError("StateManagerがAnalyzerに渡されていません。")
        self.state_manager = self.p.state_manager
        logger.info("TradePersistenceAnalyzer initialized.")

    def notify_trade(self, trade):
        super().notify_trade(trade)
        pos = self.strategy.broker.getposition(trade.data)
        symbol = trade.data._name
        
        if trade.isopen:
            entry_dt = bt.num2date(trade.dtopen).isoformat()
            self.state_manager.save_position(symbol, pos.size, pos.price, entry_dt)
            logger.info(f"StateManager: ポジションをDBに保存/更新: {symbol} (New Size: {pos.size})")
        
        if trade.isclosed:
            self.state_manager.delete_position(symbol)
            logger.info(f"StateManager: ポジションをDBから削除: {symbol}")
""",

    # 実行スクリプト
    "src/realtrade/run_realtrade.py": """
import logging
import time
import yaml
import pandas as pd
import glob
import os
import sys
import backtrader as bt

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.core.util import logger as logger_setup
from src.core import strategy as btrader_strategy
from . import config_realtrade as config
from .state_manager import StateManager
from .analyzer import TradePersistenceAnalyzer

if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'SBI':
        from .live.sbi_store import SBIStore as LiveStore
        from .live.sbi_broker import SBIBroker as LiveBroker
        from .live.sbi_data import SBIData as LiveData
    elif config.DATA_SOURCE == 'YAHOO':
        from .live.yahoo_store import YahooStore as LiveStore
        from backtrader.brokers import BackBroker as LiveBroker
        from .live.yahoo_data import YahooData as LiveData
    else:
        raise ValueError(f"サポートされていないDATA_SOURCEです: {config.DATA_SOURCE}")
else:
    from .mock.data_fetcher import MockDataFetcher

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_strategy_catalog(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.symbols = [s for s in self.symbols if s and str(s).lower() != 'nan']
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
        cerebro = bt.Cerebro(runonce=False)
        
        if config.LIVE_TRADING:
            logger.info(f"ライブモード({config.DATA_SOURCE})用のStore, Broker, DataFeedをセットアップします。")
            store = LiveStore(api_key=config.API_KEY, api_secret=config.API_SECRET) if config.DATA_SOURCE == 'SBI' else LiveStore()
            broker = LiveBroker(store=store) if config.DATA_SOURCE == 'SBI' else LiveBroker()
            cerebro.setbroker(broker)
            cerebro.broker.set_cash(config.INITIAL_CAPITAL)
            logger.info(f"-> {broker.__class__.__name__}をCerebroにセットしました。初期資金: {config.INITIAL_CAPITAL:,.0f}円")

            for symbol in self.symbols:
                data_feed = LiveData(dataname=symbol, store=store)
                cerebro.adddata(data_feed, name=str(symbol))
                cerebro.adddata(LiveData(dataname=symbol, store=store), name=f"{symbol}_medium")
                cerebro.adddata(LiveData(dataname=symbol, store=store), name=f"{symbol}_long")
            logger.info(f"-> {len(self.symbols)}銘柄の{LiveData.__name__}フィード(3階層)をCerebroに追加しました。")
        else:
            logger.info("シミュレーションモード用のBrokerとDataFeedをセットアップします。")
            data_fetcher = MockDataFetcher(symbols=self.symbols)
            broker = bt.brokers.BackBroker()
            cerebro.setbroker(broker)
            cerebro.broker.set_cash(config.INITIAL_CAPITAL)
            logger.info(f"-> 標準のBackBrokerをセットしました。初期資金: {config.INITIAL_CAPITAL:,.0f}円")
            
            if self.symbols:
                target_symbol = str(self.symbols[0])
                logger.info(f"シミュレーションは最初の銘柄 ({target_symbol}) のみで実行します。")
                
                cerebro.adddata(data_fetcher.get_data_feed(target_symbol), name=target_symbol)
                cerebro.adddata(data_fetcher.get_data_feed(target_symbol), name=f"{target_symbol}_medium")
                cerebro.adddata(data_fetcher.get_data_feed(target_symbol), name=f"{target_symbol}_long")
                
                logger.info(f"-> 銘柄 {target_symbol} のMockデータフィード(3階層)をCerebroに追加しました。")
            else:
                logger.warning("取引対象の銘柄が見つかりません。")

        
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        logger.info("-> 永続化用AnalyzerをCerebroに追加しました。")

        cerebro.addstrategy(btrader_strategy.DynamicStrategy,
                            strategy_catalog=self.strategy_catalog,
                            strategy_assignments=self.strategy_assignments,
                            live_trading=config.LIVE_TRADING)
        logger.info(f"-> DynamicStrategyをCerebroに追加しました (live_trading={config.LIVE_TRADING})。")
        
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

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime')
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

if __name__ == '__main__':
    main()
""",

    # --- live/ パッケージ ---
    "src/realtrade/live/sbi_store.py": """
import logging
logger = logging.getLogger(__name__)
class SBIStore:
    def __init__(self, api_key, api_secret, paper_trading=True):
        self.api_key, self.api_secret, self.paper_trading = api_key, api_secret, paper_trading
        logger.info(f"SBIStoreを初期化しました。ペーパートレード: {self.paper_trading}")
    def get_cash(self): return 10000000 
    def get_value(self): return 10000000
    def get_positions(self): return [] 
    def place_order(self, order): logger.info(f"【API連携】注文送信: {order}"); return f"api-order-{id(order)}"
    def cancel_order(self, order_id): logger.info(f"【API連携】注文キャンセル送信: OrderID={order_id}")
    def get_historical_data(self, dataname, timeframe, compression, period): logger.info(f"【API連携】履歴データ取得: {dataname} ({period}本)"); return None
""",
    "src/realtrade/live/sbi_broker.py": """
import backtrader as bt
import logging
logger = logging.getLogger(__name__)
class SBIBroker(bt.brokers.BrokerBase):
    def __init__(self, store):
        super(SBIBroker, self).__init__(); self.store = store; self.orders = []; logger.info("SBIBrokerを初期化しました。")
    def start(self):
        super(SBIBroker, self).start(); self.cash = self.store.get_cash(); self.value = self.store.get_value(); logger.info(f"Brokerを開始しました。現金: {self.cash}, 資産価値: {self.value}")
    def buy(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, **kwargs):
        order = super().buy(owner, data, size, price, plimit, exectype, valid, tradeid, oco, trailamount, trailpercent, **kwargs); order.api_id = self.store.place_order(order); self.orders.append(order); self.notify(order); return order
    def sell(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, **kwargs):
        order = super().sell(owner, data, size, price, plimit, exectype, valid, tradeid, oco, trailamount, trailpercent, **kwargs); order.api_id = self.store.place_order(order); self.orders.append(order); self.notify(order); return order
    def cancel(self, order):
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]: self.store.cancel_order(order.api_id); order.cancel(); self.notify(order)
        return order
""",
    "src/realtrade/live/sbi_data.py": """
import backtrader as bt; import pandas as pd; from datetime import datetime; import time; import threading; import random; import logging
logger = logging.getLogger(__name__)
class SBIData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1),)
    def __init__(self):
        store = self.p.store;
        if not store: raise ValueError("SBIDataにはstoreの指定が必要です。")
        symbol = self.p.dataname; df = store.get_historical_data(dataname=symbol, timeframe=self.p.timeframe, compression=self.p.compression, period=200)
        if df is None or df.empty: logger.warning(f"[{symbol}] 履歴データがありません。"); df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
        self.p.dataname = df; super(SBIData, self).__init__(); self.symbol_str = symbol; self._thread = None; self._stop_event = threading.Event()
    def start(self):
        super(SBIData, self).start(); logger.info(f"[{self.symbol_str}] SBIDataスレッドを開始します..."); self._thread = threading.Thread(target=self._run); self._thread.start()
    def stop(self):
        logger.info(f"[{self.symbol_str}] SBIDataスレッドを停止します..."); self._stop_event.set();
        if self._thread is not None: self._thread.join()
        super(SBIData, self).stop()
    def _run(self):
        while not self._stop_event.is_set():
            try:
                time.sleep(5); last_close = self.close[-1] if len(self.close) > 0 else 1000; new_open = self.open[0] = self.close[0] if len(self.open) > 0 else last_close; new_close = new_open * (1 + random.uniform(-0.005, 0.005))
                self.lines.datetime[0] = bt.date2num(datetime.now()); self.lines.open[0] = new_open; self.lines.high[0] = max(new_open, new_close) * (1 + random.uniform(0, 0.002)); self.lines.low[0] = min(new_open, new_close) * (1 - random.uniform(0, 0.002)); self.lines.close[0] = new_close; self.lines.volume[0] = random.randint(100, 5000); self.put_notification(self.LIVE)
            except Exception as e: logger.error(f"データ取得スレッドでエラーが発生: {e}"); time.sleep(10)
""",
    "src/realtrade/live/yahoo_store.py": """
import logging; import yfinance as yf; import pandas as pd
logger = logging.getLogger(__name__)
class YahooStore:
    def __init__(self, **kwargs): logger.info("YahooStoreを初期化しました。")
    def get_cash(self): return 0
    def get_value(self): return 0
    def get_positions(self): return []
    def place_order(self, order): return None
    def cancel_order(self, order_id): return None
    def get_historical_data(self, dataname, period, interval='1m'):
        logger.info(f"【Yahoo Finance】履歴データ取得: {dataname} ({period} {interval})")
        ticker = f"{dataname}.T"
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
            if df.empty: logger.warning(f"{ticker}のデータ取得に失敗しました。"); return pd.DataFrame()
            if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]
            df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
            # [修正] タイムゾーン情報を削除
            if df.index.tz is not None: df.index = df.index.tz_localize(None)
            df['openinterest'] = 0.0; logger.info(f"{dataname}の履歴データを{len(df)}件取得しました。"); return df
        except Exception as e: logger.error(f"{ticker}のデータ取得中にエラー: {e}"); return pd.DataFrame()
""",
    "src/realtrade/live/yahoo_data.py": """
import backtrader as bt; from datetime import datetime, timedelta; import time; import threading; import logging; import yfinance as yf; import pandas as pd
logger = logging.getLogger(__name__)
class YahooData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1), ('drop_newest', True),)
    
    def __init__(self):
        store = self.p.store
        if not store: raise ValueError("YahooDataにはstoreの指定が必要です。")
        symbol = self.p.dataname
        df = store.get_historical_data(dataname=symbol, period='7d', interval='1m')
        if df.empty:
            logger.warning(f"[{symbol}] 履歴データがありません。")
            df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
        
        if self.p.drop_newest and not df.empty:
            df = df.iloc[:-1]

        self.p.dataname = df
        super(YahooData, self).__init__()
        self.symbol_str = symbol
        self._thread = None
        self._stop_event = threading.Event()
        self.last_dt = df.index[-1] if not df.empty else None

    def start(self):
        super(YahooData, self).start()
        logger.info(f"[{self.symbol_str}] YahooDataスレッドを開始します...")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.symbol_str}] YahooDataスレッドを停止します...")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        super(YahooData, self).stop()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                time.sleep(60)
                ticker = f"{self.symbol_str}.T"
                df = yf.download(ticker, period='2d', interval='1m', progress=False, auto_adjust=False)
                
                if df.empty:
                    self._put_heartbeat()
                    continue

                if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]
                if df.columns.duplicated().any(): df = df.loc[:, ~df.columns.duplicated(keep='first')]
                
                # [修正] タイムゾーン情報を削除
                if df.index.tz is not None: df.index = df.index.tz_localize(None)
                
                latest_bar_dt = df.index[-1]
                
                if self.last_dt is None or latest_bar_dt > self.last_dt:
                    latest_bar = df.iloc[-1]
                    self.lines.datetime[0] = bt.date2num(latest_bar.name.to_pydatetime())
                    self.lines.open[0] = latest_bar['Open']
                    self.lines.high[0] = latest_bar['High']
                    self.lines.low[0] = latest_bar['Low']
                    self.lines.close[0] = latest_bar['Close']
                    self.lines.volume[0] = latest_bar['Volume']
                    self.lines.openinterest[0] = 0.0
                    self.put_notification(self.LIVE)
                    self.last_dt = latest_bar_dt
                    logger.debug(f"[{self.symbol_str}] 新しいデータを追加: {latest_bar.name}")
                else:
                    self._put_heartbeat()

            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}")
                time.sleep(60)
    
    def _put_heartbeat(self):
        \"\"\"データ更新がない場合に、最後のデータを元に空のバーを供給する\"\"\"
        if len(self) > 0:
            self.lines.datetime[0] = self.lines.datetime[-1] + self.p.compression * 60 / (24 * 60 * 60) # 1分進める
            self.lines.open[0] = self.lines.close[-1]
            self.lines.high[0] = self.lines.close[-1]
            self.lines.low[0] = self.lines.close[-1]
            self.lines.close[0] = self.lines.close[-1]
            self.lines.volume[0] = 0
            self.lines.openinterest[0] = 0
            self.put_notification(self.LIVE)
            logger.debug(f"[{self.symbol_str}] データ更新なし、ハートビートを供給。")
""",

    # --- mock/ パッケージ ---
    "src/realtrade/mock/data_fetcher.py": """
import backtrader as bt; import pandas as pd; from datetime import datetime; import numpy as np; import logging
logger = logging.getLogger(__name__)
class MockDataFetcher:
    def __init__(self, symbols):
        self.symbols = symbols; self.data_feeds = {s: None for s in symbols}; logger.info("MockDataFetcherを初期化しました。")
    def get_data_feed(self, symbol):
        if self.data_feeds.get(symbol) is None: self.data_feeds[symbol] = bt.feeds.PandasData(dataname=self._generate_dummy_data(symbol, 200))
        return self.data_feeds[symbol]
    def _generate_dummy_data(self, symbol, period):
        logger.info(f"MockDataFetcher: ダミー履歴データ生成 - 銘柄:{symbol}, 期間:{period}本")
        dates = pd.date_range(end=datetime.now(), periods=period, freq='1min').tz_localize(None); start_price = np.random.uniform(1000, 5000); prices = []
        current_price = start_price
        for _ in range(period): current_price *= (1 + np.random.normal(loc=0.0001, scale=0.01)); prices.append(current_price)
        df = pd.DataFrame(index=dates); df['open'] = prices; df['close'] = [p * (1 + np.random.normal(0, 0.005)) for p in prices]
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.005, size=period)); df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.005, size=period))
        df['volume'] = np.random.randint(100, 10000, size=period); return df
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
        if not content and not filename.endswith("__init__.py"):
             continue
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"  - ファイル作成: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- 6. realtradeパッケージの生成を開始します ---")
    create_files(realtrade_files)
    print("realtradeパッケージの生成が完了しました。")

