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

# [修正] ログレベルをDEBUGに変更
# LOG_LEVEL = logging.DEBUG
LOG_LEVEL = logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')

# === Excel Bridge Settings ===
# trading_hub.xlsmへの絶対パスまたは相対パスを指定
EXCEL_WORKBOOK_PATH = os.path.join(BASE_DIR, "external", "trading_hub.xlsm")
""",

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

    "src/realtrade/run_realtrade.py": """import logging
import time as time_module
import yaml
import pandas as pd
import glob
import os
import sys
import threading
from datetime import datetime, time, timedelta

# --- Project Root Setup ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.core.util import logger as logger_setup, notifier
from . import config_realtrade as config
from .bridge.excel_connector import ExcelConnector
from .position_synchronizer import PositionSynchronizer
from .cerebro_factory import CerebroFactory

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        self.trade_data = self._load_trade_data(config.RECOMMEND_FILE_PATTERN)
        
        self.strategy_assignments = pd.Series(
            self.trade_data['戦略名'].values, 
            index=self.trade_data['銘柄'].astype(str)
        ).to_dict()
        
        self.statistics_map = {}
        cols_to_load = ['Kelly_Adj', 'Kelly_Raw']
        for _, row in self.trade_data.iterrows():
            key = (row['戦略名'], str(row['銘柄']))
            stats = {col: row[col] for col in cols_to_load if col in row}
            self.statistics_map[key] = stats

        self.symbols = list(self.strategy_assignments.keys())
        
        self.threads = []
        self.cerebro_instances = []
        self.strategy_instances = {}
        self.stop_event = threading.Event()
        
        self.connector = ExcelConnector(workbook_path=config.EXCEL_WORKBOOK_PATH)
        
        self.factory = CerebroFactory(
            self.strategy_catalog, 
            self.base_strategy_params, 
            config.DATA_DIR,
            self.statistics_map
        )
        self.synchronizer = PositionSynchronizer(self.connector, self.strategy_instances, self.stop_event)

    def _load_yaml(self, fp):
        with open(fp, 'r', encoding='utf-8') as f: return yaml.safe_load(f)
        
    def _load_trade_data(self, pattern):
        files = glob.glob(pattern)
        if not files: raise FileNotFoundError(f"Recommendation file not found: {pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"Loading recommended strategies and stats from: {latest_file}")
        df = pd.read_csv(latest_file)
        if 'Kelly_Adj' not in df.columns or 'Kelly_Raw' not in df.columns:
            logger.warning(f"警告: {latest_file} に 'Kelly_Adj' または 'Kelly_Raw' が見つかりません。")
        return df

    def _run_cerebro(self, cerebro_instance):
        try:
            cerebro_instance.run()
        except Exception as e:
            logger.error(f"Cerebro thread crashed: {e}", exc_info=True)
        logger.info(f"Cerebro thread finished: {threading.current_thread().name}")

    def start(self):
        logger.info("Starting RealtimeTrader components...")
        self.connector.start()

        for symbol in self.symbols:
            strategy_name = self.strategy_assignments.get(str(symbol))
            if not strategy_name:
                logger.warning(f"No strategy assigned for symbol {symbol}. Skipping.")
                continue
            
            cerebro = self.factory.create_instance(symbol, strategy_name, self.connector)
            
            if cerebro:
                self.cerebro_instances.append(cerebro)
                self.strategy_instances[str(symbol)] = cerebro.strats[0][0]
                
                t = threading.Thread(target=self._run_cerebro, args=(cerebro,), name=f"Cerebro-{symbol}", daemon=True)
                self.threads.append(t)
                t.start()
        
        self.synchronizer.start()
        logger.info("RealtimeTrader started successfully.")

    def stop(self):
        \"\"\"全コンポーネントを安全に停止し、データを確実に保存する。\"\"\"
        logger.info("Stopping RealtimeTrader...")
        self.stop_event.set()

        # 1. Primary Data (5分足) の保存
        logger.info("Saving primary history data (5m)...")
        saved_symbols = []
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'save_history'):
                if hasattr(cerebro.datas[0], 'flush'):
                    cerebro.datas[0].flush()
                cerebro.datas[0].save_history()
                saved_symbols.append(cerebro.datas[0].symbol)

        # 2. Resampled Data (60分足, 日足) の生成と保存
        logger.info("Generating and saving resampled data (60m, 1D)...")
        for symbol in saved_symbols:
            try:
                self._regenerate_resampled_csvs(symbol)
            except Exception as e:
                logger.error(f"[{symbol}] Failed to regenerate resampled CSVs: {e}", exc_info=True)

        # 3. データフィードの停止
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'stop'):
                cerebro.datas[0].stop()

        # 4. スレッドの終了待機
        if self.synchronizer.is_alive():
            self.synchronizer.join(timeout=5)
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=5)
        
        # 5. Excelコネクタの停止
        self.connector.stop()
        logger.info("RealtimeTrader stopped.")

    def _regenerate_resampled_csvs(self, symbol):
        \"\"\"
        [修正]
        1. 5分足ファイル: 名前を固定せず、glob検索で最新のファイルを特定して読み込む。
        2. 保存ファイル: YYYYMMDD形式で保存する。
        \"\"\"
        # ▼▼▼ 修正: 5分足ファイルの特定ロジック ▼▼▼
        search_pattern = os.path.join(config.DATA_DIR, f"{symbol}_5m_*.csv")
        files = glob.glob(search_pattern)
        
        if not files:
            logger.warning(f"[{symbol}] 5m source file not found: {search_pattern}")
            return

        # 最新のファイルを特定
        file_5m = max(files, key=os.path.getctime)
        # ▲▲▲ 修正ここまで ▲▲▲

        # データの読み込み
        try:
            df = pd.read_csv(file_5m, parse_dates=['datetime'], index_col='datetime')
        except Exception as e:
            logger.error(f"[{symbol}] Failed to read 5m file {file_5m}: {e}")
            return

        if df.empty: return

        # タイムゾーン情報の統一
        if df.index.tz is None:
            df.index = df.index.tz_localize('Asia/Tokyo')
        else:
            df.index = df.index.tz_convert('Asia/Tokyo')

        targets = [('60min', '60m'), ('D', '1D')]
        aggregation = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        
        # ▼▼▼ 修正: 保存ファイル名の日付部分 (YYYYMMDD) ▼▼▼
        date_str = datetime.now().strftime('%Y%m%d')
        # ▲▲▲ 修正ここまで ▲▲▲

        for rule, suffix in targets:
            try:
                resampled_df = df.resample(rule, closed='left', label='left').agg(aggregation)
                resampled_df.dropna(inplace=True)

                # XXXX_60m_YYYYMMDD.csv の形式で保存
                save_path = os.path.join(config.DATA_DIR, f"{symbol}_{suffix}_{date_str}.csv")
                resampled_df.to_csv(save_path)
                logger.info(f"[{symbol}] {suffix} CSV updated: {save_path}")
            except Exception as e:
                logger.error(f"[{symbol}] Error resampling to {suffix}: {e}")

# --- Supervisor Functions ---

def is_market_active(now: datetime) -> bool:
    if now.weekday() >= 5: return False
    current_time = now.time()
    return time(9, 0) <= current_time <= time(15, 30)

def get_seconds_until_next_open(now: datetime) -> float:
    next_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now >= next_open: next_open += timedelta(days=1)
    while next_open.weekday() >= 5: next_open += timedelta(days=1)
    return (next_open - now).total_seconds()

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime', level=config.LOG_LEVEL)
    notifier.start_notifier()
    trader = None

    logger.info("=== StockAutoV3 Realtime Supervisor Started ===")

    try:
        while True:
            now = datetime.now()
            
            if is_market_active(now):
                if trader is None:
                    logger.info(f"市場オープン ({now.strftime('%H:%M')})。トレーダーを起動します。")
                    trader = RealtimeTrader()
                    trader.start()
                else:
                    time_module.sleep(1)
            else:
                if trader is not None:
                    logger.info(f"市場クローズ ({now.strftime('%H:%M')})。トレーダーを停止・データ保存します。")
                    trader.stop()
                    trader = None
                    logger.info("トレーダーの停止が完了しました。")

                wait_seconds = get_seconds_until_next_open(now)
                logger.info(f"次回市場開始まで待機モードに入ります。({wait_seconds / 3600:.1f}時間後)")
                
                sleep_chunk = 60
                while wait_seconds > 0:
                    sleep_time = min(wait_seconds, sleep_chunk)
                    time_module.sleep(sleep_time)
                    wait_seconds -= sleep_time
                    
    except KeyboardInterrupt:
        logger.info("Ctrl+C detected. Shutting down gracefully.")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred in the main thread: {e}", exc_info=True)
    finally:
        if trader:
            logger.info("Performing final cleanup...")
            trader.stop()
        notifier.stop_notifier()
        logger.info("Application has been shut down.")

if __name__ == '__main__':
    main()""",

    "src/realtrade/position_synchronizer.py": """import threading
import time
import logging

logger = logging.getLogger(__name__)

class PositionSynchronizer(threading.Thread):
    \"\"\"
    外部(Excel)と内部(システム)のポジションを同期させる責務を持つ。
    threading.Threadを継承し、独立したスレッドで動作する。
    \"\"\"
    SYNC_INTERVAL = 1.0 # 1秒ごとに同期

    def __init__(self, connector, strategies, stop_event, **kwargs):
        super().__init__(daemon=True, name="PositionSyncThread", **kwargs)
        self.connector = connector
        self.strategies = strategies # {symbol: strategy_instance}
        self.stop_event = stop_event
        logger.info("PositionSynchronizer initialized.")

    def run(self):
        \"\"\"スレッドのメインループ。定期的に同期処理を実行する。\"\"\"
        logger.info("Position synchronization thread started.")
        while not self.stop_event.is_set():
            try:
                # 外部(Excel)のポジションを取得
                excel_positions = self.connector.get_positions()

                # 内部(ストラテジー)のポジションを収集
                internal_positions = {}
                # スレッドセーフなアクセスのため、辞書のコピーを作成
                strategies_copy = self.strategies.copy()
                for symbol, strategy in strategies_copy.items():
                    if hasattr(strategy, 'realtime_phase_started') and strategy.realtime_phase_started and strategy.position:
                        internal_positions[symbol] = {
                            'size': strategy.position.size,
                            'price': strategy.position.price
                        }

                # 同期処理を実行
                self._sync_positions(excel_positions, internal_positions)
            
            except Exception as e:
                logger.error(f"Error in position synchronization loop: {e}", exc_info=True)

            time.sleep(self.SYNC_INTERVAL)
        logger.info("Position synchronization thread stopped.")

    def _sync_positions(self, excel_pos, internal_pos):
        \"\"\"2つのポジション情報を比較し、差異があれば同期する。\"\"\"
        all_symbols = set(excel_pos.keys()) | set(internal_pos.keys())

        for symbol in all_symbols:
            strategy = self.strategies.get(symbol)
            if not strategy or not (hasattr(strategy, 'realtime_phase_started') and strategy.realtime_phase_started):
                continue

            e_pos = excel_pos.get(symbol)
            i_pos = internal_pos.get(symbol)

            if e_pos and not i_pos:
                # 新規検知: Excelにあり、内部にない -> 内部状態に注入
                logger.info(f"[{symbol}] New position detected. Injecting into strategy: {e_pos}")
                strategy.inject_position(e_pos['size'], e_pos['price'])
            
            elif not e_pos and i_pos:
                # 決済検知: 内部にあり、Excelにない -> 内部状態をクリア
                logger.info(f"[{symbol}] Closed position detected. Clearing strategy state.")
                strategy.force_close_position()

            elif e_pos and i_pos:
                # 差異検知: 両方に存在するが内容が異なる -> Excelの情報に更新
                if e_pos['size'] != i_pos['size'] or e_pos['price'] != i_pos['price']:
                    logger.info(f"[{symbol}] Position difference detected. Updating strategy: {e_pos}")
                    strategy.inject_position(e_pos['size'], e_pos['price'])
""",

    "src/realtrade/cerebro_factory.py": """import backtrader as bt
import copy
import yaml
import logging
import os
import glob
import pandas as pd
from datetime import datetime

from .strategy import RealTradeStrategy
from .rakuten.rakuten_broker import RakutenBroker
from .rakuten.rakuten_data import RakutenData

logger = logging.getLogger(__name__)

class CerebroFactory:
    def __init__(self, strategy_catalog, base_strategy_params, data_dir, statistics_map):
        self.strategy_catalog = strategy_catalog
        self.base_strategy_params = base_strategy_params
        self.data_dir = data_dir
        self.statistics_map = statistics_map
        logger.info("CerebroFactory initialized.")

    def create_instance(self, symbol: str, strategy_name: str, connector):
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not entry_strategy_def:
            logger.warning(f"Strategy definition not found for '{strategy_name}'. Skipping symbol {symbol}.")
            return None

        strategy_params = copy.deepcopy(self.base_strategy_params)
        strategy_params.update(entry_strategy_def)
        strategy_params['strategy_name'] = strategy_name

        try:
            cerebro = bt.Cerebro(runonce=False)
            cerebro.setbroker(RakutenBroker(bridge=connector))
            
            # 短期足設定
            short_tf_config = strategy_params['timeframes']['short']
            compression = short_tf_config['compression']
            
            # [変更] CSVファイルパスの特定
            search_pattern = os.path.join(self.data_dir, f"{symbol}_{compression}m_*.csv")
            files = glob.glob(search_pattern)
            
            hist_df = pd.DataFrame()
            save_file_path = None

            if files:
                latest_file = max(files, key=os.path.getctime)
                save_file_path = latest_file
                try:
                    df = pd.read_csv(latest_file, index_col='datetime', parse_dates=True)
                    if not df.empty:
                        # タイムゾーン情報を除去してBacktraderに渡す(BT内部で処理するため)
                        if df.index.tz is not None: df.index = df.index.tz_localize(None)
                        df.columns = [x.lower() for x in df.columns]
                        hist_df = df
                        logger.info(f"[{symbol}] Loaded {len(hist_df)} bars from {latest_file}")
                except Exception as e:
                    logger.warning(f"[{symbol}] Could not load historical data from {latest_file}: {e}")
            
            # ファイルが存在しない場合は新規作成パスを設定 (年単位)
            if not save_file_path:
                year = datetime.now().year
                save_file_path = os.path.join(self.data_dir, f"{symbol}_{compression}m_{year}.csv")
                logger.info(f"[{symbol}] 新規保存先を設定: {save_file_path}")

            # [変更] RakutenDataにsave_fileを渡す
            primary_data = RakutenData(
                dataname=hist_df,
                bridge=connector,
                symbol=symbol,
                timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
                compression=short_tf_config['compression'],
                save_file=save_file_path
            )
            cerebro.adddata(primary_data, name=str(symbol))

            # リサンプリング
            for tf_name in ['medium', 'long']:
                if tf_config := strategy_params['timeframes'].get(tf_name):
                    cerebro.resampledata(
                        primary_data,
                        timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                        compression=tf_config['compression'],
                        name=tf_name
                    )
            
            # 戦略追加
            stats_key = (strategy_name, str(symbol))
            symbol_statistics = self.statistics_map.get(stats_key, {})
            strategy_components = { 'statistics': symbol_statistics }
            
            cerebro.addstrategy(
                RealTradeStrategy, 
                strategy_params=strategy_params, 
                strategy_components=strategy_components
            )
            
            return cerebro

        except Exception as e:
            logger.error(f"[{symbol}] Failed to create Cerebro instance: {e}", exc_info=True)
            return None""",

    "src/realtrade/bar_builder.py": """from datetime import datetime, timedelta

class BarBuilder:
    \"\"\"
    リアルタイムのTickデータストリームを受け取り、定義された時間枠の
    OHLCV（始値・高値・安値・終値・出来高）バーを構築することに特化したクラス。
    \"\"\"
    def __init__(self, interval_minutes: int = 5):
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive.")
        self._interval = timedelta(minutes=interval_minutes)
        self._current_bar = None
        self._last_cumulative_volume = 0.0

    def add_tick(self, timestamp: datetime, price: float, cumulative_volume: float) -> dict | None:
        \"\"\"
        新しいTickデータを処理し、バーが完成した場合にそのバー(dict)を返す。
        形成中の場合はNoneを返す。
        \"\"\"
        if price is None or cumulative_volume is None:
            return None # 不正なデータは無視

        # このTickが属するべきバーの開始時刻を計算 (より堅牢な方法に修正)
        interval_minutes = int(self._interval.total_seconds() / 60)
        new_minute = timestamp.minute - (timestamp.minute % interval_minutes)
        bar_start_time = timestamp.replace(minute=new_minute, second=0, microsecond=0)

        completed_bar = None

        # 形成中のバーがあり、時間枠が切り替わった場合 -> バー完成
        if self._current_bar and self._current_bar['timestamp'] != bar_start_time:
            completed_bar = self._current_bar
            self._current_bar = None

        # 新しいバーを開始
        if self._current_bar is None:
            # 差分出来高を計算（セッション跨ぎやリセットを考慮）
            if self._last_cumulative_volume > 0 and cumulative_volume >= self._last_cumulative_volume:
                tick_volume = cumulative_volume - self._last_cumulative_volume
            else:
                tick_volume = cumulative_volume # 初回Tickまたは出来高リセット時

            self._current_bar = {
                'timestamp': bar_start_time,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': tick_volume
            }
        # 既存のバーを更新
        else:
            self._current_bar['high'] = max(self._current_bar['high'], price)
            self._current_bar['low'] = min(self._current_bar['low'], price)
            self._current_bar['close'] = price
            
            # 差分出来高を計算して加算
            if self._last_cumulative_volume > 0 and cumulative_volume >= self._last_cumulative_volume:
                tick_volume = cumulative_volume - self._last_cumulative_volume
                self._current_bar['volume'] += tick_volume
        
        # 最後に処理した累計出来高を更新
        self._last_cumulative_volume = cumulative_volume
        
        return completed_bar

    def flush(self) -> dict | None:
        \"\"\"
        現在形成途中のバーを強制的に返し、内部状態をリセットする。
        取引終了時などに使用する。
        \"\"\"
        if self._current_bar:
            final_bar = self._current_bar
            self._current_bar = None
            self._last_cumulative_volume = 0.0
            return final_bar
        return None""",

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

    "src/realtrade/implementations/event_handler.py": """import logging
import backtrader as bt
from src.core.strategy.event_handler import BaseEventHandler

class RealTradeEventHandler(BaseEventHandler):
    \"\"\"
    リアルタイムトレード用のイベントハンドラ。
    BaseEventHandlerを継承し、約定時の通知、TP/SL計算、状態保存の実装を提供する。
    \"\"\"
    def __init__(self, strategy, notifier, state_manager=None):
        super().__init__(strategy, notifier)
        self.state_manager = state_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    # --- BaseEventHandler の抽象メソッドを実装 ---

    def _handle_entry_completion(self, order):
        \"\"\"エントリー約定時の処理: ログ、通知、TP/SL計算、DB保存\"\"\"
        self.logger.info(f"エントリー約定: Size={order.executed.size:.2f} @ {order.executed.price:.2f}")
        
        # 1. 通知 (約定報告)
        # ※ここは「約定」の通知なので、シンプルで良い（詳細な条件は「発注」時に通知済み）
        subject = f"【RT】エントリー約定 ({self.strategy.data0._name})"
        body = (f"日時: {bt.num2date(order.executed.dt).isoformat()}\\n"
                f"銘柄: {self.strategy.data0._name}\\n"
                f"数量: {order.executed.size:.2f}\\n"
                f"価格: {order.executed.price:.2f}")
        self.notifier.send(subject, body, immediate=True)

        # 2. 決済価格の再計算 (ExitSignalGenerator連携) ★重要: これがないと決済されない
        self.strategy.exit_signal_generator.calculate_and_set_exit_prices(
            entry_price=order.executed.price, 
            is_long=order.isbuy()
        )
        
        # 3. DB保存
        self._update_trade_persistence(order)

    def _handle_exit_completion(self, order):
        \"\"\"決済約定時の処理: ログ、通知、DB更新\"\"\"
        pnl = order.executed.pnl
        exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
        
        self.logger.info(f"決済完了: PNL={pnl:,.2f} ({exit_reason})")
        
        # 通知
        subject = f"【RT】決済完了 - {exit_reason} ({self.strategy.data0._name})"
        body = (f"銘柄: {self.strategy.data0._name}\\n"
                f"実現損益: {pnl:,.0f}円\\n"
                f"価格: {order.executed.price:.2f}")
        self.notifier.send(subject, body, immediate=True)

        # 決済価格リセット
        esg = self.strategy.exit_signal_generator
        esg.tp_price, esg.sl_price = 0.0, 0.0
        
        # DB更新
        self._update_trade_persistence(order)

    # --- その他のオーバーライド ---

    def on_entry_order_placed(self, trade_type, size, reason, entry_price, tp_price, sl_price):
        \"\"\"エントリー注文発注時の処理\"\"\"
        # 親クラスのログ出力
        super().on_entry_order_placed(trade_type, size, reason, entry_price, tp_price, sl_price)
        
        # --- ▼▼▼ メール通知フォーマット (ユーザー指定) ▼▼▼ ---
        is_long = trade_type == 'long'
        symbol_name = self.strategy.data0._name
        
        subject = f"【RT】新規注文発注 ({symbol_name})"
        
        body = (
            f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\\n"
            f"銘柄: {symbol_name}\\n"
            f"方向: {'BUY' if is_long else 'SELL'}\\n"
            f"数量: {size:.2f}\\n"
            f"価格: {entry_price:.1f}\\n"
            f"TP: {tp_price:.1f}\\n"
            f"SL: {sl_price:.1f}\\n"
            f"--- エントリー根拠 ---\\n"
            f"{reason}"
        )
        self.notifier.send(subject, body, immediate=True)
        # --- ▲▲▲ ここまで ▲▲▲ ---

    def _handle_order_failure(self, order):
        \"\"\"注文失敗時の処理\"\"\"
        super()._handle_order_failure(order)
        subject = f"【RT】注文失敗/キャンセル ({self.strategy.data0._name})"
        body = f"ステータス: {order.getstatusname()}"
        self.notifier.send(subject, body, immediate=True)

    def on_data_status(self, data, status):
        \"\"\"データフィードの状態変化\"\"\"
        status_names = ['DELAYED', 'LIVE', 'DISCONNECTED', 'UNKNOWN']
        s_name = status_names[status] if 0 <= status < len(status_names) else str(status)
        self.logger.info(f"Data Status Changed: {data._name} -> {s_name}")

    # --- ヘルパーメソッド ---

    def _update_trade_persistence(self, order):
        \"\"\"DB上のポジション情報を更新する\"\"\"
        if not self.state_manager:
            return
            
        symbol = order.data._name
        position = self.strategy.broker.getposition(order.data)
        
        if position.size == 0:
            self.state_manager.delete_position(symbol)
            self.logger.info(f"StateManager: ポジションをDBから削除: {symbol}")
        else:
            entry_dt = bt.num2date(order.executed.dt).isoformat()
            self.state_manager.save_position(symbol, position.size, position.price, entry_dt)
            self.logger.info(f"StateManager: ポジションをDBに保存/更新: {symbol} (Size: {position.size})")""",

    "src/realtrade/implementations/exit_signal_generator.py": """from src.core.strategy.exit_signal_generator import BaseExitSignalGenerator

class RealTradeExitSignalGenerator(BaseExitSignalGenerator):
    \"\"\"
    リアルタイムトレード用の出口信号生成クラス。
    毎barの価格を監視し、決済条件(TP/SL)を判定する。
    トレーリングストップのロジックもここに実装される。
    \"\"\"
    def __init__(self, strategy, order_manager):
        super().__init__(strategy, order_manager)

    def check_exit_conditions(self):
        \"\"\"
        現在の価格とポジションを確認し、TP/SL条件に合致すれば決済注文を出す。
        \"\"\"
        pos = self.strategy.getposition()
        # ポジションがない場合は何もしない
        if not pos or pos.size == 0:
            return

        is_long = pos.size > 0
        current_price = self.strategy.datas[0].close[0]
        logger = self.strategy.logger

        if is_long:
            # --- ロングポジションの場合 ---
            
            # 利確判定 (Take Profit)
            if self.tp_price != 0 and current_price >= self.tp_price:
                logger.log(f"ライブ: 利確条件ヒット(Long)。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
                self.order_manager.close_position()
                return

            # 損切り判定 (Stop Loss)
            if self.sl_price != 0:
                if current_price <= self.sl_price:
                    logger.log(f"ライブ: 損切り条件ヒット(Long)。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                    self.order_manager.close_position()
                    return
                
                # トレーリングストップの更新 (価格上昇に合わせてSLを引き上げる)
                # リスク幅(risk_per_share)を維持して追従
                if self.risk_per_share > 0:
                    new_sl_price = current_price - self.risk_per_share
                    if new_sl_price > self.sl_price:
                        logger.log(f"ライブ: SL価格を更新(Long) {self.sl_price:.2f} -> {new_sl_price:.2f}")
                        self.sl_price = new_sl_price
        else:
            # --- ショートポジションの場合 ---
            
            # 利確判定 (Take Profit)
            if self.tp_price != 0 and current_price <= self.tp_price:
                logger.log(f"ライブ: 利確条件ヒット(Short)。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
                self.order_manager.close_position()
                return

            # 損切り判定 (Stop Loss)
            if self.sl_price != 0:
                if current_price >= self.sl_price:
                    logger.log(f"ライブ: 損切り条件ヒット(Short)。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                    self.order_manager.close_position()
                    return
                
                # トレーリングストップの更新 (価格下落に合わせてSLを引き下げる)
                if self.risk_per_share > 0:
                    new_sl_price = current_price + self.risk_per_share
                    if new_sl_price < self.sl_price:
                        logger.log(f"ライブ: SL価格を更新(Short) {self.sl_price:.2f} -> {new_sl_price:.2f}")
                        self.sl_price = new_sl_price""",

    "src/realtrade/implementations/order_manager.py": """import logging
from src.core.strategy.order_manager import BaseOrderManager

logger = logging.getLogger(__name__)

class RealTradeOrderManager(BaseOrderManager):
    \"\"\"
    リアルタイムトレード用の注文マネージャ。
    \"\"\"
    def __init__(self, strategy, params, method, event_handler, statistics=None):
        # BaseOrderManager.__init__の引数に合わせて呼び出す
        # statisticsはリアルタイムのみで使用
        super().__init__(strategy, params, method, event_handler, statistics=statistics)""",

    "src/realtrade/implementations/strategy_notifier.py": """import logging
from datetime import datetime, timedelta
from src.core.util import notifier
from src.core.strategy.strategy_notifier import BaseStrategyNotifier

class RealTradeStrategyNotifier(BaseStrategyNotifier):
    \"\"\"
    リアルタイムトレード用の通知クラス（遅延警告機能付き）
    \"\"\"
    def __init__(self, strategy):
        super().__init__(strategy)
        self.logger = logging.getLogger(self.__class__.__name__)

    def send(self, subject, body, immediate=False):
        
        # 1. 履歴データ再生中の判定 (念のための二重チェック)
        # strategy.next()側でも制御されているが、安全のためここでもチェック
        if not getattr(self.strategy, 'realtime_phase_started', False):
            self.logger.debug(f"履歴データ供給中のため通知を抑制: {subject}")
            return
        
        # 2. バーの日時取得と検証
        try:
            # 最新のバーの日時を取得
            bar_datetime = self.strategy.data0.datetime.datetime(0)
        except IndexError:
            # バーがまだ存在しない（start()時など）場合は、比較せずそのまま送信試行
            self.logger.warning(f"バーデータが存在しないため、時間差チェックをスキップ: {subject}")
            notifier.send_email(subject, body, immediate=immediate)
            return

        # タイムゾーン情報の除去（比較のため）
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)

        # 3. 遅延チェック (15分以上遅れているか)
        current_time = datetime.now()
        allowed_delay = timedelta(minutes=15) # 異常遅延とみなす閾値
        time_diff = current_time - bar_datetime
        is_delayed = time_diff > allowed_delay

        # 4. 警告の追記
        if is_delayed:
            delay_minutes = int(time_diff.total_seconds() / 60)
            
            # 決済通知 (件名に "決済" や "Stop Loss" を含む) かどうかで警告レベルを変更
            if "決済" in subject or "Stop Loss" in subject:
                subject = f"【!!!決済遅延警告: {delay_minutes}分前!!!】{subject}"
            else:
                subject = f"【エントリー遅延警告: {delay_minutes}分前】{subject}"
            
            warning_msg = f\"\"\"警告: このシグナルは {delay_minutes}分前 ({bar_datetime.isoformat()}) のデータに基づいています。
現在の価格と乖離している可能性があります。
------------------------------------

\"\"\"
            body = warning_msg + body
            self.logger.warning(f"データ遅延検知: {delay_minutes}分遅れ - {subject}")
        
        # 5. 通知の実行
        self.logger.debug(f"通知リクエストを発行: {subject}")
        notifier.send_email(subject, body, immediate=immediate)""",

    "src/realtrade/strategy.py": """import backtrader as bt
from src.core.strategy.base import BaseStrategy

# 実装クラスのインポート
from .implementations.order_manager import RealTradeOrderManager
from .implementations.event_handler import RealTradeEventHandler
# ▼▼▼ 修正箇所: インポート元を strategy_notifier に変更 ▼▼▼
from .implementations.strategy_notifier import RealTradeStrategyNotifier
from .implementations.exit_signal_generator import RealTradeExitSignalGenerator

class RealTradeStrategy(BaseStrategy):
    \"\"\"
    リアルタイムトレード用の戦略クラス。
    \"\"\"
    def __init__(self):
        self.realtime_phase_started = False
        super().__init__()

    def _setup_components(self, params, components):
        \"\"\"
        リアルタイムトレード用のコンポーネントをセットアップする
        \"\"\"
        state_manager = components.get('state_manager')
        statistics = components.get('statistics')
        sizing_params = params.get('sizing', {})
        
        # 設定からメソッドを取得
        method = sizing_params.get('realtrade_method', 'risk_based')
        
        # 通知・イベントハンドラの初期化
        self.notifier = RealTradeStrategyNotifier(self)
        self.event_handler = RealTradeEventHandler(self, self.notifier, state_manager=state_manager)
        
        # OrderManagerの初期化
        self.order_manager = RealTradeOrderManager(
            self, 
            sizing_params, 
            method,
            self.event_handler,
            statistics=statistics
        )
        
        # 出口戦略ジェネレータの初期化
        self.exit_signal_generator = RealTradeExitSignalGenerator(self, self.order_manager)

    def next(self):
        # 履歴データの供給完了を検知してフラグを立てる
        if not self.realtime_phase_started:
            if hasattr(self.datas[0], 'history_supplied') and self.datas[0].history_supplied:
                self.logger.log("リアルタイムフェーズに移行しました。")
                self.realtime_phase_started = True
        
        # リアルタイムフェーズの場合のみ実行
        if self.realtime_phase_started:
            super().next()

    def notify_data(self, data, status, *args, **kwargs):
        self.event_handler.on_data_status(data, status)
    
    def inject_position(self, size, price):
        if self.position.size == size and self.position.price == price:
            return
        self.logger.log(f"外部からポジションを注入: Size={size}, Price={price}")
        self.position.size = size
        self.position.price = price
        self.exit_signal_generator.calculate_and_set_exit_prices(entry_price=price, is_long=(size > 0))

    def force_close_position(self):
        if not self.position: return
        self.logger.log(f"外部からの指示により内部ポジション({self.position.size})を決済します。")
        self.close()"""
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