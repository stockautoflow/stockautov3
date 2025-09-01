import os
import sys
import copy

# ==============================================================================
# ファイル: create_realtrade.py
# 実行方法: python create_realtrade.py
# Ver. 00-47
# 変更点:
#   - src/realtrade/run_realtrade.py:
#     - カスタムCommissionInfoの適用方法を、正しいAPI呼び出しである
#       `cerebro.broker.addcommissioninfo(...)` に修正。
# ==============================================================================

project_files = {
    "src/realtrade/__init__.py": """""",

    "src/realtrade/live/__init__.py": """""",

    "src/realtrade/mock/__init__.py": """""",

    "src/realtrade/config_realtrade.py": """import os
import logging
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LIVE_TRADING = True
#DATA_SOURCE = 'YAHOO'
DATA_SOURCE = 'RAKUTEN'
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
if LIVE_TRADING:
    print(f"<<< ライブモード ({DATA_SOURCE}) で起動します >>>")
    if DATA_SOURCE == 'SBI' and (not API_KEY or "YOUR_API_KEY_HERE" in API_KEY or not API_SECRET or "YOUR_API_SECRET_HERE" in API_SECRET):
        print("警告: SBI設定でAPIキーまたはシークレットが設定されていません。")
else:
    print("<<< シミュレーションモードで起動します (MockDataFetcher使用) >>>")
INITIAL_CAPITAL = 5000000
MAX_CONCURRENT_ORDERS = 5
RECOMMEND_FILE_PATTERN = os.path.join(BASE_DIR, "results", "evaluation", "*", "all_recommend_*.csv")
LOG_LEVEL = logging.DEBUG # or logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')

# === Excel Bridge Settings ===
# trading_hub.xlsmへの絶対パスまたは相対パスを指定
EXCEL_WORKBOOK_PATH = os.path.join(BASE_DIR, "external", "trading_hub.xlsm")""",

    "src/realtrade/state_manager.py": """
import sqlite3
import logging
import os
import threading

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.lock = threading.Lock()
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
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS positions (
                        symbol TEXT PRIMARY KEY, size REAL NOT NULL,
                        price REAL NOT NULL, entry_datetime TEXT NOT NULL)
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
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(sql, (str(symbol), size, price, entry_datetime))
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"ポジション保存エラー: {e}")

    def load_positions(self):
        positions = {}
        sql = "SELECT symbol, size, price, entry_datetime FROM positions"
        try:
            with self.lock:
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
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(sql, (str(symbol),))
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"ポジション削除エラー: {e}")
""",

    "src/realtrade/analyzer.py": """import backtrader as bt
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
        
        # isopen, isclosedに関わらず、現在のブローカーのポジション状態を正とする
        symbol = trade.data._name
        pos = self.strategy.broker.getposition(trade.data)

        if pos.size == 0:
            # ポジションがゼロになった場合 -> DBから削除
            self.state_manager.delete_position(symbol)
            logger.info(f"StateManager: ポジションをDBから削除（Size=0）: {symbol}")
        else:
            # ポジションが建玉された、または変更された場合 -> DBに保存/更新
            # entry_datetimeは最新のトレード開始日時で更新
            entry_dt = bt.num2date(trade.dtopen).isoformat()
            self.state_manager.save_position(symbol, pos.size, pos.price, entry_dt)
            logger.info(f"StateManager: ポジションをDBに保存/更新: {symbol} (New Size: {pos.size})")""",

    "src/realtrade/run_realtrade.py": """import logging, time, yaml, pandas as pd, glob, os, sys, backtrader as bt, threading, copy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path: sys.path.append(project_root)

from src.core.util import logger as logger_setup, notifier
from . import config_realtrade as config
from .state_manager import StateManager
from .strategy import RealTradeStrategy # <-- [修正] 新しいストラテジーをインポート

if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'RAKUTEN':
        from .bridge.excel_bridge import ExcelBridge
        from .rakuten.rakuten_data import RakutenData
        from .rakuten.rakuten_broker import RakutenBroker
else:
    from .mock.data_fetcher import MockDataFetcher # シミュレーション用

class NoCreditInterest(bt.CommInfoBase):
    def get_credit_interest(self, data, pos, dt): return 0.0

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(os.path.join(config.BASE_DIR, "results", "realtrade", "realtrade_state.db"))
        self.persisted_positions = self.state_manager.load_positions()
        self.threads, self.cerebro_instances = [], []
        self.bridge = None
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            self.bridge = ExcelBridge(workbook_path=config.EXCEL_WORKBOOK_PATH)

    def _load_yaml(self, fp):
        with open(fp, 'r', encoding='utf-8') as f: return yaml.safe_load(f)
        
    def _load_strategy_assignments(self, pattern):
        latest_file = max(glob.glob(pattern), key=os.path.getctime)
        df = pd.read_csv(latest_file)
        return pd.Series(df.iloc[:, 0].values, index=df.iloc[:, 1].astype(str)).to_dict()

    def _run_cerebro(self, cerebro_instance):
        try: cerebro_instance.run()
        finally: logger.info(f"Cerebroスレッド ({threading.current_thread().name}) 終了。")

    def _create_cerebro_for_symbol(self, symbol):
        strategy_name = self.strategy_assignments.get(str(symbol))
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not strategy_name or not entry_strategy_def:
            logger.warning(f"銘柄 {symbol} の戦略定義が見つかりません。")
            return None
        strategy_params = copy.deepcopy(self.base_strategy_params)
        strategy_params.update(entry_strategy_def)
        cerebro = bt.Cerebro(runonce=False)
        
        # --- [修正] ライブデータフィードの初期化をここで行う ---
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if not self.bridge: return None
            cerebro.setbroker(RakutenBroker(bridge=self.bridge))
            cerebro.broker.set_cash(10**12); cerebro.broker.addcommissioninfo(NoCreditInterest())
            
            short_tf_config = strategy_params['timeframes']['short']
            compression = short_tf_config['compression']
            search_pattern = os.path.join(config.DATA_DIR, f"{symbol}_{compression}m_*.csv")
            files = glob.glob(search_pattern)
            hist_df = pd.DataFrame()
            if files:
                try:
                    df = pd.read_csv(max(files, key=os.path.getctime), index_col='datetime', parse_dates=True)
                    if df.index.tz is not None: df.index = df.index.tz_localize(None)
                    df.columns = [x.lower() for x in df.columns]; hist_df = df
                except Exception as e:
                    logger.error(f"[{symbol}] 過去データCSV読み込み失敗: {e}")
            
            primary_data = RakutenData(dataname=hist_df, bridge=self.bridge, symbol=symbol,
                timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']), compression=short_tf_config['compression'])
            cerebro.adddata(primary_data, name=str(symbol))

            for tf_name in ['medium', 'long']:
                if tf_config := strategy_params['timeframes'].get(tf_name):
                    cerebro.resampledata(primary_data, timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                                         compression=tf_config['compression'], name=tf_name)
        else: # Mock/Yahooなど (未実装のためスキップ)
            return None
        
        # [修正] 新しいRealTradeStrategyと、必要なコンポーネントを渡す
        strategy_components = {
            'live_trading': True,
            'persisted_position': self.persisted_positions.get(str(symbol)),
            'state_manager': self.state_manager
        }
        cerebro.addstrategy(
            RealTradeStrategy,
            strategy_params=strategy_params,
            strategy_components=strategy_components
        )
        return cerebro

    def start(self):
        if self.bridge: self.bridge.start()
        for symbol in self.symbols:
            if cerebro := self._create_cerebro_for_symbol(symbol):
                self.cerebro_instances.append(cerebro)
                t = threading.Thread(target=self._run_cerebro, args=(cerebro,), name=f"Cerebro-{symbol}", daemon=False)
                self.threads.append(t); t.start()

    def stop(self):
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'stop'):
                cerebro.datas[0].stop()
        if self.bridge: self.bridge.stop()
        for t in self.threads: t.join(timeout=10)
        if self.state_manager: self.state_manager.close()

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime', level=config.LOG_LEVEL)
    notifier.start_notifier()
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while any(t.is_alive() for t in trader.threads): time.sleep(5)
    except KeyboardInterrupt: logger.info("Ctrl+C検知。システムを停止します。")
    finally:
        if trader: trader.stop()
        notifier.stop_notifier()

if __name__ == '__main__':
    main()""",

    "src/realtrade/live/yahoo_store.py": """
import logging; import yfinance as yf; import pandas as pd
logger = logging.getLogger(__name__)
class YahooStore:
    def __init__(self, **kwargs): logger.info("YahooStoreを初期化しました。")
    def get_historical_data(self, dataname, period, interval='1m'):
        logger.info(f"【Yahoo Finance】履歴データ取得: {dataname} ({period} {interval})")
        ticker = f"{dataname}.T"
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
            if df.empty: 
                logger.warning(f"{ticker}のデータ取得に失敗しました。")
                return pd.DataFrame()

            if isinstance(df.columns, pd.MultiIndex):
                logger.debug(f"[{dataname}] 履歴データでMultiIndexを検出。自銘柄のデータを抽出します。")
                if ticker in df.columns.get_level_values(1):
                     df = df.xs(ticker, axis=1, level=1)
                else:
                     logger.warning(f"[{dataname}] 履歴データの応答に自銘柄データが含まれていません。スキップします。")
                     return pd.DataFrame()

            df.columns = [x.lower() for x in df.columns]

            is_duplicate = df.columns.duplicated(keep='first')
            if is_duplicate.any():
                logger.warning(f"[{dataname}] 履歴データに重複列を検出、削除しました: {df.columns[is_duplicate].tolist()}")
                df = df.loc[:, ~is_duplicate]

            if df.index.tz is not None: df.index = df.index.tz_localize(None)
            df['openinterest'] = 0.0
            logger.info(f"{dataname}の履歴データを{len(df)}件取得しました。")
            return df
        except Exception as e: 
            logger.error(f"{ticker}のデータ取得中にエラー: {e}", exc_info=True)
            return pd.DataFrame()
""",

    "src/realtrade/live/yahoo_data.py": """
import backtrader as bt
from datetime import datetime
import time
import threading
import logging
import yfinance as yf
import pandas as pd
from queue import Queue, Empty

logger = logging.getLogger(__name__)

class YahooData(bt.feeds.PandasData):
    params = (('store', None), ('drop_newest', True),)

    _STOP_SENTINEL = object()
    _FETCH_INTERVAL = 60
    _QUEUE_TIMEOUT = 2.0

    def __init__(self):
        symbol = self.p.dataname
        empty_df = pd.DataFrame(columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest'])
        empty_df = empty_df.set_index('datetime')
        self.p.dataname = empty_df
        super(YahooData, self).__init__()

        self.store = self.p.store
        if not self.store: raise ValueError("YahooDataにはstoreの指定が必要です。")
        self.symbol_str = symbol
        
        self.q = Queue()
        self._hist_df = None
        self._load_historical_data()

        self._thread = None
        self._stop_event = threading.Event()
        self.last_dt = None
        self.last_close_price = None

    def _load_historical_data(self):
        logger.info(f"[{self.symbol_str}] 履歴データを内部保持用に取得中...")
        self._hist_df = self.store.get_historical_data(self.symbol_str, period='7d', interval='1m')
        if self.p.drop_newest and not self._hist_df.empty:
            self._hist_df = self._hist_df.iloc[:-1]
        if self._hist_df.empty:
            logger.warning(f"[{self.symbol_str}] 履歴データが見つかりません。")

    def start(self):
        super(YahooData, self).start()
        self._thread = threading.Thread(target=self._run, daemon=False)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.symbol_str}] YahooDataスレッドに停止信号を送信...")
        self._stop_event.set()
        self.q.put(self._STOP_SENTINEL)
        if self._thread is not None:
            self._thread.join(timeout=5)
        super(YahooData, self).stop()

    def _load(self):
        if self._hist_df is not None and not self._hist_df.empty:
            row = self._hist_df.iloc[0]
            self._hist_df = self._hist_df.iloc[1:]
            self._push_bar(row)
            return True

        while True:
            try:
                item = self.q.get(timeout=self._QUEUE_TIMEOUT)
                if item is self._STOP_SENTINEL:
                    logger.info(f"[{self.symbol_str}] 停止シグナルを検知。データ供給を終了します。")
                    return False
                
                self._push_bar(item)
                return True
            except Empty:
                self._put_heartbeat()
                return True

    def _run(self):
        logger.info(f"[{self.symbol_str}] データ取得スレッド(_run)を開始しました。")
        while not self._stop_event.is_set():
            try:
                ticker_str_with_suffix = f"{self.symbol_str}.T"
                df = yf.download(tickers=ticker_str_with_suffix, period='2d', interval='1m', progress=False, auto_adjust=False)

                if not df.empty:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(f"[{self.symbol_str}] yfinanceから取得した生の列名: {df.columns.tolist()}")

                    if isinstance(df.columns, pd.MultiIndex):
                        if ticker_str_with_suffix in df.columns.get_level_values(1):
                             df = df.xs(ticker_str_with_suffix, axis=1, level=1)
                        else:
                             logger.warning(f"[{self.symbol_str}] yfinanceの応答に自銘柄のデータが含まれていません。スキップします。")
                             continue
                    
                    df.columns = [str(col).lower() for col in df.columns]

                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    
                    latest_bar_series = df.iloc[-1]
                    latest_bar_dt = latest_bar_series.name.to_pydatetime()
                    
                    if self.last_dt is None or latest_bar_dt > self.last_dt:
                        self.q.put(latest_bar_series)
                        logger.debug(f"[{self.symbol_str}] 新しいデータをキューに追加: {latest_bar_dt}")

                for _ in range(self._FETCH_INTERVAL):
                    if self._stop_event.is_set(): break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}", exc_info=True)
                time.sleep(self._FETCH_INTERVAL)
        logger.info(f"[{self.symbol_str}] データ取得スレッド(_run)を終了します。")


    def _push_bar(self, bar_series):
        bar_dt = bar_series.name.to_pydatetime()
        self.lines.datetime[0] = bt.date2num(bar_dt)
        self.lines.open[0] = float(bar_series['open'])
        self.lines.high[0] = float(bar_series['high'])
        self.lines.low[0] = float(bar_series['low'])
        self.lines.close[0] = float(bar_series['close'])
        self.lines.volume[0] = float(bar_series['volume'])
        self.lines.openinterest[0] = float(bar_series.get('openinterest', 0.0))
        self.last_close_price = bar_series['close']
        self.last_dt = bar_dt

    def _put_heartbeat(self):
        if self.last_close_price is not None:
            epsilon = 0.01
            now = datetime.now()
            self.lines.datetime[0] = bt.date2num(now)
            self.lines.high[0] = self.last_close_price + epsilon
            self.lines.low[0] = self.last_close_price
            self.lines.open[0] = self.last_close_price
            self.lines.close[0] = self.last_close_price
            self.lines.volume[0] = 0
            self.lines.openinterest[0] = 0
            logger.debug(f"[{self.symbol_str}] データ更新なし、ハートビートを供給: {now}")
""",

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
""",

    "src/realtrade/implementations/__init__.py": """
""",

    "src/realtrade/implementations/event_handler.py": """import backtrader as bt
from src.core.strategy.event_handler import BaseEventHandler

class RealTradeEventHandler(BaseEventHandler):
    \"\"\"
    [リファクタリング - 実装]
    リアルタイム取引用のイベントハンドラ。
    状態の永続化と外部通知の責務を持つ。
    \"\"\"
    def __init__(self, strategy, notifier, state_manager=None):
        super().__init__(strategy, notifier)
        self.state_manager = state_manager

    def on_entry_order_placed(self, trade_type, size, reason, tp_price, sl_price):
        super().on_entry_order_placed(trade_type, size, reason, tp_price, sl_price)
        is_long = trade_type == 'long'
        subject = f"【RT】新規注文発注 ({self.strategy.data0._name})"
        body = (f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\\n"
                f"銘柄: {self.strategy.data0._name}\\n"
                f"方向: {'BUY' if is_long else 'SELL'}\\n数量: {size:.2f}\\n"
                f"--- エントリー根拠 ---\\n{reason}")
        self.notifier.send(subject, body, immediate=True)

    def _handle_entry_completion(self, order):
        self.logger.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
        subject = f"【RT】エントリー注文約定 ({self.strategy.data0._name})"
        body = (f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\\n"
                f"約定数量: {order.executed.size:.2f}\\n約定価格: {order.executed.price:.2f}")
        self.notifier.send(subject, body, immediate=True)
        # 決済価格を再計算
        self.strategy.exit_generator.calculate_and_set_exit_prices(
            entry_price=order.executed.price, is_long=order.isbuy()
        )
        esg = self.strategy.exit_generator
        self.logger.log(f"ライブモード決済監視開始: TP={esg.tp_price:.2f}, Initial SL={esg.sl_price:.2f}")
        self._update_trade_persistence(order)

    def _handle_exit_completion(self, order):
        pnl = order.executed.pnl
        exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
        self.logger.log(f"決済完了。 PNL: {pnl:,.2f} ({exit_reason})")
        subject = f"【RT】決済完了 - {exit_reason} ({self.strategy.data0._name})"
        body = f"実現損益: {pnl:,.2f}"
        self.notifier.send(subject, body, immediate=True)
        # 決済価格リセット
        esg = self.strategy.exit_generator
        esg.tp_price, esg.sl_price = 0.0, 0.0
        self._update_trade_persistence(order)

    def _handle_order_failure(self, order):
        super()._handle_order_failure(order)
        subject = f"【RT】注文失敗/キャンセル ({self.strategy.data0._name})"
        body = f"ステータス: {order.getstatusname()}"
        self.notifier.send(subject, body, immediate=True)

    def _update_trade_persistence(self, order):
        if not self.state_manager: return
        symbol = order.data._name
        position = self.strategy.broker.getposition(order.data)
        if position.size == 0:
            self.state_manager.delete_position(symbol)
            self.logger.log(f"StateManager: ポジションをDBから削除: {symbol}")
        else:
            entry_dt = bt.num2date(order.executed.dt).isoformat()
            self.state_manager.save_position(symbol, position.size, position.price, entry_dt)
            self.logger.log(f"StateManager: ポジションをDBに保存/更新: {symbol} (Size: {position.size})")""",

    "src/realtrade/implementations/exit_signal_generator.py": """from src.core.strategy.exit_signal_generator import BaseExitSignalGenerator

class RealTradeExitSignalGenerator(BaseExitSignalGenerator):
    \"\"\"
    [リファクタリング - 実装]
    毎barの価格を監視し、決済条件を判定する。
    トレーリングストップのロジックもここに実装。
    \"\"\"
    def check_exit_conditions(self):
        pos = self.strategy.getposition()
        is_long = pos.size > 0
        current_price = self.strategy.datas[0].close[0]
        logger = self.strategy.logger

        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            logger.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            self.order_manager.close_position()
            return

        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                logger.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                self.order_manager.close_position()
                return
            # トレーリングストップの更新
            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                logger.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                self.sl_price = new_sl_price""",

    "src/realtrade/implementations/order_manager.py": """from src.core.strategy.order_manager import BaseOrderManager

class RealTradeOrderManager(BaseOrderManager):
    \"\"\"
    [リファクタリング - 実装]
    リアルタイム取引用の注文管理。
    現時点では基底クラスの振る舞いと同じ。
    将来的にブローカーAPIを直接叩く場合はここに実装する。
    \"\"\"
    pass""",

    "src/realtrade/implementations/strategy_notifier.py": """from datetime import datetime, timedelta
import logging
from src.core.util import notifier
from src.core.strategy.strategy_notifier import BaseStrategyNotifier

class RealTradeStrategyNotifier(BaseStrategyNotifier):
    \"\"\"
    [リファクタリング - 実装]
    実際に通知（メール送信など）を行う。
    \"\"\"
    def __init__(self, strategy):
        super().__init__(strategy)
        self.logger = logging.getLogger(self.__class__.__name__)

    def send(self, subject, body, immediate=False):
        bar_datetime = self.strategy.data0.datetime.datetime(0)
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)
        if datetime.now() - bar_datetime > timedelta(minutes=5):
            self.logger.debug(f"過去データに基づく通知を抑制: {subject}")
            return
        self.logger.debug(f"通知リクエストを発行: {subject}")
        notifier.send_email(subject, body, immediate=immediate)""",

    "src/realtrade/strategy.py": """from src.core.strategy.base import BaseStrategy
from .implementations.event_handler import RealTradeEventHandler
from .implementations.exit_signal_generator import RealTradeExitSignalGenerator
from .implementations.order_manager import RealTradeOrderManager
from .implementations.strategy_notifier import RealTradeStrategyNotifier

class RealTradeStrategy(BaseStrategy):
    \"\"\"
    [リファクタリング - 実装]
    リアルタイム取引に必要な全てのimplementationsコンポーネントを組み立てる「司令塔」。
    \"\"\"
    def _setup_components(self, params, components):
        state_manager = components.get('state_manager')
        
        notifier = RealTradeStrategyNotifier(self)
        self.event_handler = RealTradeEventHandler(self, notifier, state_manager=state_manager)
        self.order_manager = RealTradeOrderManager(self, params.get('sizing', {}), self.event_handler)
        self.exit_generator = RealTradeExitSignalGenerator(self, self.order_manager)"""
}


def create_files(files_dict):
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
    create_files(project_files)
    print("realtradeパッケージの生成が完了しました。")