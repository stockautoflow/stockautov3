#2
import logging
import time as time_module
import yaml
import pandas as pd
import glob
import os
import sys
import threading
from datetime import datetime, time, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        # ▼▼▼ 修正箇所: 09:00まで待機するロジックを追加 ▼▼▼
        symbol_name = "Unknown"
        try:
            if cerebro_instance.datas:
                symbol_name = cerebro_instance.datas[0]._name
            
            # 停止シグナルが来ていない間、9:00になるまで待機
            while not self.stop_event.is_set():
                current_time = datetime.now().time()
                # 9:00以降であればループを抜けて実行開始
                if current_time >= time(9, 0):
                    break
                
                # ログ過多を防ぐため、スリープを入れる
                time_module.sleep(1)
            
            # 待機中に停止シグナルが来た場合は実行せずに終了
            if self.stop_event.is_set():
                logger.info(f"[{symbol_name}] 起動待機中に停止シグナルを受信しました。")
                return

            cerebro_instance.run()

        except Exception as e:
            logger.error(f"[{symbol_name}] Cerebro thread crashed: {e}", exc_info=True)
        # ▲▲▲ 修正箇所ここまで ▲▲▲
        
        logger.info(f"Cerebro thread finished: {threading.current_thread().name}")

    def _init_single_instance(self, symbol):
        """1銘柄分のCerebroインスタンス生成を行う（スレッドプールから呼ばれる）"""
        try:
            strategy_name = self.strategy_assignments.get(str(symbol))
            if not strategy_name:
                logger.warning(f"No strategy assigned for symbol {symbol}. Skipping.")
                return None
            
            # ここで重い処理 (CSV読み込み) が走る
            cerebro = self.factory.create_instance(symbol, strategy_name, self.connector)
            return (symbol, cerebro)
        except Exception as e:
            logger.error(f"Failed to initialize strategy for {symbol}: {e}", exc_info=True)
            return None

    def start(self):
        logger.info("Starting RealtimeTrader components...")
        self.connector.start()

        logger.info(f"Initializing {len(self.symbols)} strategies in parallel...")
        
        # 並列初期化
        max_workers = min(32, len(self.symbols)) if len(self.symbols) > 0 else 1
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {executor.submit(self._init_single_instance, sym): sym for sym in self.symbols}
            
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        _, cerebro = result
                        if cerebro:
                            self.cerebro_instances.append(cerebro)
                            self.strategy_instances[str(symbol)] = cerebro.strats[0][0]
                except Exception as e:
                    logger.error(f"Exception during initialization for {symbol}: {e}")

        logger.info("All strategies initialized. Starting threads...")

        for cerebro in self.cerebro_instances:
            symbol_name = cerebro.datas[0]._name 
            t = threading.Thread(target=self._run_cerebro, args=(cerebro,), name=f"Cerebro-{symbol_name}", daemon=True)
            self.threads.append(t)
            t.start()
        
        self.synchronizer.start()
        logger.info("RealtimeTrader started successfully.")

    def stop(self):
        """全コンポーネントを安全に停止し、データを確実に保存する。"""
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
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(self._regenerate_resampled_csvs, sym) for sym in saved_symbols]
            for f in as_completed(futures):
                pass 

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
        """
        1. 5分足ファイル: glob検索で最新のファイルを特定して読み込む。
        2. 保存ファイル: YYYYMMDD形式で保存する。
        """
        search_pattern = os.path.join(config.DATA_DIR, f"{symbol}_5m_*.csv")
        files = glob.glob(search_pattern)
        
        if not files:
            logger.warning(f"[{symbol}] 5m source file not found: {search_pattern}")
            return

        file_5m = max(files, key=os.path.getctime)

        try:
            df = pd.read_csv(file_5m, parse_dates=['datetime'], index_col='datetime')
        except Exception as e:
            logger.error(f"[{symbol}] Failed to read 5m file {file_5m}: {e}")
            return

        if df.empty: return

        if df.index.tz is None:
            df.index = df.index.tz_localize('Asia/Tokyo')
        else:
            df.index = df.index.tz_convert('Asia/Tokyo')

        targets = [('60min', '60m'), ('D', '1D')]
        aggregation = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        date_str = datetime.now().strftime('%Y%m%d')

        for rule, suffix in targets:
            try:
                resampled_df = df.resample(rule, closed='left', label='left').agg(aggregation)
                resampled_df.dropna(inplace=True)
                save_path = os.path.join(config.DATA_DIR, f"{symbol}_{suffix}_{date_str}.csv")
                resampled_df.to_csv(save_path)
                logger.info(f"[{symbol}] {suffix} CSV updated: {save_path}")
            except Exception as e:
                logger.error(f"[{symbol}] Error resampling to {suffix}: {e}")

# --- Supervisor Functions ---

def is_market_active(now: datetime) -> bool:
    if now.weekday() >= 5: return False
    current_time = now.time()
    # 08:50 から監視を開始 (起動時間確保のため)
    return time(8, 50) <= current_time <= time(15, 30)

def get_seconds_until_next_open(now: datetime) -> float:
    # 08:50 に起動するように調整
    next_open = now.replace(hour=8, minute=50, second=0, microsecond=0)
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
                    logger.info(f"市場オープン準備 ({now.strftime('%H:%M')})。トレーダーを起動します。")
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
                logger.info(f"次回市場開始(08:50)まで待機モードに入ります。({wait_seconds / 3600:.1f}時間後)")
                
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
    main()