import logging
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

# --- Local Imports ---
from src.core.util import logger as logger_setup, notifier
from . import config_realtrade as config
from .bridge.excel_connector import ExcelConnector
from .position_synchronizer import PositionSynchronizer
from .cerebro_factory import CerebroFactory

logger = logging.getLogger(__name__)

class RealtimeTrader:
    """
    リアルタイムトレードの実行単位（Worker）。
    スーパーバイザーによって生成・破棄される。
    """
    def __init__(self):
        # 1. 設定ファイルの読み込み
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        
        # 推奨戦略と統計情報のロード
        self.trade_data = self._load_trade_data(config.RECOMMEND_FILE_PATTERN)
        
        # 戦略割り当てマップを作成
        self.strategy_assignments = pd.Series(
            self.trade_data['戦略名'].values, 
            index=self.trade_data['銘柄'].astype(str)
        ).to_dict()
        
        # ケリー基準を含む統計情報マップを作成
        self.statistics_map = {}
        cols_to_load = ['Kelly_Adj', 'Kelly_Raw']
        for _, row in self.trade_data.iterrows():
            key = (row['戦略名'], str(row['銘柄']))
            stats = {col: row[col] for col in cols_to_load if col in row}
            self.statistics_map[key] = stats

        self.symbols = list(self.strategy_assignments.keys())
        
        # 2. 状態管理変数の初期化
        self.threads = []
        self.cerebro_instances = []
        self.strategy_instances = {} # {symbol: strategy_instance}
        self.stop_event = threading.Event()
        
        # 3. 主要コンポーネントの初期化
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
        """全コンポーネントを起動し、リアルタイム取引を開始する。"""
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
        """全コンポーネントを安全に停止し、データを保存する。"""
        logger.info("Stopping RealtimeTrader...")
        self.stop_event.set()

        # 1. データの保存 (Future Proofing: 次のステップで実装されるsave_historyを呼び出す準備)
        logger.info("Saving history data for all feeds...")
        for cerebro in self.cerebro_instances:
            if cerebro.datas:
                # Primary data feed (RakutenData) は通常 datas[0]
                data_feed = cerebro.datas[0]
                if hasattr(data_feed, 'save_history'):
                    # 念のため flush してから保存
                    if hasattr(data_feed, 'flush'):
                        try:
                            data_feed.flush()
                        except Exception as e:
                            logger.error(f"Error flushing data feed: {e}")
                    try:
                        data_feed.save_history()
                    except Exception as e:
                        logger.error(f"Error saving history: {e}")

        # 2. Cerebroデータフィードの停止
        # これにより、min() iterable empty エラーの発生源を断つ
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'stop'):
                cerebro.datas[0].stop()

        # 3. スレッドの終了待機
        if self.synchronizer.is_alive():
            self.synchronizer.join(timeout=5)
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=5)
        
        # 4. Excelコネクタの停止
        self.connector.stop()
        logger.info("RealtimeTrader stopped.")

# --- Supervisor Functions ---

def is_market_active(now: datetime) -> bool:
    """
    現在時刻が市場稼働時間内（平日 09:00 - 15:30）かを判定する。
    昼休み中もプロセス維持のため True を返す。
    """
    if now.weekday() >= 5: # 土(5), 日(6)
        return False
    
    current_time = now.time()
    # 09:00 <= now <= 15:30
    start_time = time(9, 0)
    end_time = time(15, 30)
    
    return start_time <= current_time <= end_time

def get_seconds_until_next_open(now: datetime) -> float:
    """
    次の市場開始時刻（平日09:00）までの秒数を計算する。
    """
    # 基準は今日の09:00
    next_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # もし今日の09:00を過ぎていたら（つまり夕方なら）、明日の09:00にする
    if now >= next_open:
        next_open += timedelta(days=1)
    
    # 週末スキップ（土日なら月曜まで進める）
    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)
        
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
                # --- [A] 市場稼働時間 ---
                if trader is None:
                    logger.info(f"市場オープン ({now.strftime('%H:%M')})。トレーダーを起動します。")
                    trader = RealtimeTrader()
                    trader.start()
                else:
                    # 稼働中は負荷をかけないよう短くスリープ
                    time_module.sleep(1)
            else:
                # --- [B] 市場時間外 ---
                if trader is not None:
                    logger.info(f"市場クローズ ({now.strftime('%H:%M')})。トレーダーを停止・データ保存します。")
                    trader.stop()
                    trader = None
                    logger.info("トレーダーの停止が完了しました。")

                # 次回起動までの待機処理
                wait_seconds = get_seconds_until_next_open(now)
                wait_hours = wait_seconds / 3600
                
                logger.info(f"次回市場開始まで待機モードに入ります。({wait_hours:.1f}時間後)")
                
                # 長時間スリープを分割して、Ctrl+Cに反応できるようにする
                sleep_chunk = 60 # 60秒ごとにチェック
                while wait_seconds > 0:
                    sleep_time = min(wait_seconds, sleep_chunk)
                    time_module.sleep(sleep_time)
                    wait_seconds -= sleep_time
                    
                    # 待機中に日付が変わったり時間が経過するので、
                    # ループを抜けて外側のwhile Trueで再評価させるのが安全
                    break 

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