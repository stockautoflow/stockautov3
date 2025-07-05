import os
import sys
import copy

# ==============================================================================
# ファイル: create_realtrade.py
# 実行方法: python create_realtrade.py
# Ver. 00-18
# 変更点:
#   - run_realtrade.py:
#     - メインループの制御を、より堅牢なthreading.Eventを用いる方式に変更。
#       これにより、スレッドの起動タイミングに依存しない、安定した待機処理を実現します。
# ==============================================================================

project_files = {
    "src/realtrade/__init__.py": "",
    "src/realtrade/live/__init__.py": "",
    "src/realtrade/mock/__init__.py": "",
    "src/realtrade/config_realtrade.py": """
import os
import logging
from dotenv import load_dotenv
load_dotenv()
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LIVE_TRADING = True
DATA_SOURCE = 'YAHOO'
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
LOG_LEVEL = logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')
""",
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
    "src/realtrade/run_realtrade.py": """
import logging
import time
import yaml
import pandas as pd
import glob
import os
import sys
import backtrader as bt
import threading
import copy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.core.util import logger as logger_setup
from src.core import strategy as btrader_strategy
from src.core.data_preparer import prepare_data_feeds
from . import config_realtrade as config
from .state_manager import StateManager
from .analyzer import TradePersistenceAnalyzer

if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'YAHOO':
        from .live.yahoo_store import YahooStore as LiveStore
    else:
        raise ValueError(f"サポートされていないDATA_SOURCEです: {config.DATA_SOURCE}")
else:
    from .mock.data_fetcher import MockDataFetcher

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(os.path.join(config.BASE_DIR, "results", "realtrade", "realtrade_state.db"))
        self.threads = []
        self.stop_event = threading.Event()

    def _load_yaml(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"設定ファイル '{filepath}' が見つかりません。")
            raise
        
    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files:
            raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"最新の対応ファイルをロード: {latest_file}")
        df = pd.read_csv(latest_file)
        return pd.Series(df.iloc[:, 0].values, index=df.iloc[:, 1].astype(str)).to_dict()

    def _run_cerebro(self, cerebro_instance):
        try:
            cerebro_instance.run()
        except Exception as e:
            logger.error(f"Cerebroスレッド ({threading.current_thread().name}) でエラーが発生: {e}", exc_info=True)
        finally:
            logger.info(f"Cerebroスレッド ({threading.current_thread().name}) が終了しました。")

    def _create_cerebro_for_symbol(self, symbol):
        cerebro = bt.Cerebro(runonce=False)
        store = LiveStore() if config.LIVE_TRADING and config.DATA_SOURCE == 'YAHOO' else None
        broker = bt.brokers.BackBroker()
        cerebro.setbroker(broker)
        cerebro.broker.set_cash(config.INITIAL_CAPITAL)
        
        strategy_name = self.strategy_assignments.get(str(symbol))
        if not strategy_name:
            logger.warning(f"銘柄 {symbol} に割り当てられた戦略がありません。スキップします。")
            return None
            
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not entry_strategy_def:
            logger.warning(f"戦略カタログに '{strategy_name}' が見つかりません。スキップします。")
            return None

        strategy_params = copy.deepcopy(self.base_strategy_params)
        strategy_params.update(entry_strategy_def)

        success = prepare_data_feeds(cerebro, strategy_params, symbol, config.DATA_DIR,
                                     is_live=config.LIVE_TRADING, live_store=store)
        if not success:
            return None

        cerebro.addstrategy(btrader_strategy.DynamicStrategy,
                            strategy_params=strategy_params,
                            live_trading=config.LIVE_TRADING)
        
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        return cerebro

    def start(self):
        logger.info("システムを開始します。")
        for symbol in self.symbols:
            logger.info(f"--- 銘柄 {symbol} のセットアップを開始 ---")
            cerebro_instance = self._create_cerebro_for_symbol(symbol)
            if cerebro_instance:
                t = threading.Thread(target=self._run_cerebro, args=(cerebro_instance,), name=f"Cerebro-{symbol}", daemon=True)
                self.threads.append(t)
                t.start()
                logger.info(f"Cerebroスレッド (Cerebro-{symbol}) を開始しました。")

    def stop(self):
        logger.info("システムを停止します。")
        self.stop_event.set()
        logger.info("全Cerebroスレッドの終了を待機中...")
        for t in self.threads:
            t.join(timeout=5)
        if self.state_manager: self.state_manager.close()
        logger.info("システムが正常に停止しました。")

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime')
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        trader.stop_event.wait()
    except KeyboardInterrupt:
        logger.info("\\nCtrl+Cを検知しました。システムを優雅に停止します。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
    logger.info("--- リアルタイムトレードシステム終了 ---")

if __name__ == '__main__':
    main()
""",
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
                df.columns = df.columns.get_level_values(0)
            df.columns = [x.lower() for x in df.columns]
            if df.index.tz is not None: df.index = df.index.tz_localize(None)
            df['openinterest'] = 0.0
            logger.info(f"{dataname}の履歴データを{len(df)}件取得しました。")
            return df
        except Exception as e: 
            logger.error(f"{ticker}のデータ取得中にエラー: {e}")
            return pd.DataFrame()
""",
    "src/realtrade/live/yahoo_data.py": """
import backtrader as bt; from datetime import datetime; import time; import threading; import logging; import yfinance as yf; import pandas as pd
logger = logging.getLogger(__name__)
class YahooData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1), ('drop_newest', True),)
    
    def __init__(self):
        store = self.p.store
        if not store: raise ValueError("YahooDataにはstoreの指定が必要です。")
        symbol = self.p.dataname
        interval_map = {(bt.TimeFrame.Days, 1): '1d', (bt.TimeFrame.Minutes, 60): '60m', (bt.TimeFrame.Minutes, 1): '1m'}
        interval = interval_map.get((self.p.timeframe, self.p.compression), '1m')
        period = '7d' if interval == '1m' else '2y'
        df = store.get_historical_data(dataname=symbol, period=period, interval=interval)
        if df.empty:
            logger.warning(f"[{symbol}] 履歴データがありません。")
            df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
        if self.p.drop_newest and not df.empty: df = df.iloc[:-1]
        self.p.dataname = df
        super(YahooData, self).__init__()
        self.symbol_str = symbol
        self._thread = None
        self._stop_event = threading.Event()
        self.last_dt = df.index[-1].to_pydatetime() if not df.empty else None

    def start(self):
        super(YahooData, self).start()
        logger.info(f"[{self.symbol_str}] YahooDataスレッドを開始します...")
        self._thread = threading.Thread(target=self._run, daemon=False)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.symbol_str}] YahooDataスレッドを停止します...")
        self._stop_event.set()
        if self._thread is not None: self._thread.join()
        super(YahooData, self).stop()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                ticker = f"{self.symbol_str}.T"
                df = yf.download(ticker, period='2d', interval='1m', progress=False, auto_adjust=False)
                new_data_pushed = False
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.columns = [x.lower() for x in df.columns]
                    if df.index.tz is not None: df.index = df.index.tz_localize(None)
                    latest_bar_dt = df.index[-1].to_pydatetime()
                    if self.last_dt is None or latest_bar_dt > self.last_dt:
                        latest_bar = df.iloc[-1]
                        self.lines.datetime[0] = bt.date2num(latest_bar.name)
                        self.lines.open[0], self.lines.high[0], self.lines.low[0], self.lines.close[0], self.lines.volume[0] = latest_bar['open'], latest_bar['high'], latest_bar['low'], latest_bar['close'], latest_bar['volume']
                        self.lines.openinterest[0] = 0.0
                        self.put_notification(self.LIVE)
                        self.last_dt = latest_bar_dt
                        new_data_pushed = True
                        logger.debug(f"[{self.symbol_str}] 新しいデータを追加: {latest_bar.name}")
                if not new_data_pushed: self._put_heartbeat()
                time.sleep(60)
            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}")
                time.sleep(60)
    
    def _put_heartbeat(self):
        if len(self) > 0:
            self.lines.datetime[0] = bt.date2num(datetime.now())
            self.lines.open[0] = self.lines.close[-1]
            self.lines.high[0] = self.lines.close[-1]
            self.lines.low[0] = self.lines.close[-1]
            self.lines.close[0] = self.lines.close[-1]
            self.lines.volume[0], self.lines.openinterest[0] = 0, 0
            self.put_notification(self.LIVE)
            logger.debug(f"[{self.symbol_str}] データ更新なし、ハートビートを供給。")
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
"""
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
