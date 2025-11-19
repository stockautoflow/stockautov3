import logging
import time
import yaml
import pandas as pd
import glob
import os
import sys
import threading

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
    # [v2.0]
    # アプリケーション全体のライフサイクルを管理するオーケストレーター。
    # ケリー基準値を含む統計マップを生成し、Factoryに渡す。
    def __init__(self):
        # 1. 設定ファイルの読み込み
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        
        # === ▼▼▼ v2.0 変更 (1/3) : 統計情報のロードとマップ生成 ▼▼▼ ===
        # 1. (変更) メソッド名を変更し、推奨戦略と統計情報をロード
        self.trade_data = self._load_trade_data(config.RECOMMEND_FILE_PATTERN)
        
        # 2. (新規) 戦略割り当てマップを作成 { 銘柄コード -> 戦略名 }
        self.strategy_assignments = pd.Series(
            self.trade_data['戦略名'].values, 
            index=self.trade_data['銘柄'].astype(str)
        ).to_dict()
        
        # 3. (新規) ケリー基準を含む統計情報マップを作成
        #    { (戦略名, 銘柄コード): {Kelly_Adj: "...", Kelly_Raw: "..."} }
        self.statistics_map = {}
        cols_to_load = ['Kelly_Adj', 'Kelly_Raw'] # 両方読み込む
        for _, row in self.trade_data.iterrows():
            key = (row['戦略名'], str(row['銘柄']))
            stats = {col: row[col] for col in cols_to_load if col in row}
            self.statistics_map[key] = stats

        self.symbols = list(self.strategy_assignments.keys())
        # === ▲▲▲ v2.0 変更 (1/3) ▲▲▲ ===
        
        # 2. 状態管理変数の初期化
        self.threads = []
        self.cerebro_instances = []
        self.strategy_instances = {} # {symbol: strategy_instance}
        self.stop_event = threading.Event()
        
        # 3. 主要コンポーネントの初期化
        self.connector = ExcelConnector(workbook_path=config.EXCEL_WORKBOOK_PATH)
        
        # === ▼▼▼ v2.0 変更 (2/3) : Factoryに statistics_map を渡す ▼▼▼ ===
        self.factory = CerebroFactory(
            self.strategy_catalog, 
            self.base_strategy_params, 
            config.DATA_DIR,
            self.statistics_map # <-- 新規追加
        )
        # === ▲▲▲ v2.0 変更 (2/3) ▲▲▲ ===
        
        self.synchronizer = PositionSynchronizer(self.connector, self.strategy_instances, self.stop_event)

    def _load_yaml(self, fp):
        with open(fp, 'r', encoding='utf-8') as f: return yaml.safe_load(f)
        
    # === ▼▼▼ v2.0 変更 (3/3) : メソッド名変更とDataFrame返却 ▼▼▼ ===
    def _load_trade_data(self, pattern):
        # (旧 _load_strategy_assignments)
        # all_recommend_*.csv からDataFrameをロードする
        files = glob.glob(pattern)
        if not files: raise FileNotFoundError(f"Recommendation file not found: {pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"Loading recommended strategies and stats from: {latest_file}")
        df = pd.read_csv(latest_file)
        # ケリー基準カラムが存在するかチェック
        if 'Kelly_Adj' not in df.columns or 'Kelly_Raw' not in df.columns:
            logger.warning(f"警告: {latest_file} に 'Kelly_Adj' または 'Kelly_Raw' が見つかりません。")
        return df
    # === ▲▲▲ v2.0 変更 (3/3) ▲▲▲ ===

    def _run_cerebro(self, cerebro_instance):
        try:
            cerebro_instance.run()
        except Exception as e:
            logger.error(f"Cerebro thread crashed: {e}", exc_info=True)
        logger.info(f"Cerebro thread finished: {threading.current_thread().name}")

    def start(self):
        # 全コンポーネントを起動し、リアルタイム取引を開始する。
        logger.info("Starting RealtimeTrader...")
        self.connector.start()

        for symbol in self.symbols:
            strategy_name = self.strategy_assignments.get(str(symbol))
            if not strategy_name:
                logger.warning(f"No strategy assigned for symbol {symbol}. Skipping.")
                continue
            
            # (変更) factory.create_instance に渡す引数をシンプルにする
            cerebro = self.factory.create_instance(symbol, strategy_name, self.connector)
            
            if cerebro:
                self.cerebro_instances.append(cerebro)
                # ストラテジーインスタンスを同期用に保持
                self.strategy_instances[str(symbol)] = cerebro.strats[0][0]
                
                t = threading.Thread(target=self._run_cerebro, args=(cerebro,), name=f"Cerebro-{symbol}", daemon=True)
                self.threads.append(t)
                t.start()
        
        # Cerebroスレッドの起動後に同期スレッドを起動
        self.synchronizer.start()
        logger.info("RealtimeTrader started successfully.")

    def stop(self):
        """全コンポーネントを安全に停止する。"""
        logger.info("Stopping RealtimeTrader...")
        self.stop_event.set()

        # [修正] データフィード停止前に、未完成の最終バーをフラッシュする
        logger.info("Flushing any pending data bars...")
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'flush'):
                try:
                    cerebro.datas[0].flush()
                except Exception as e:
                    logger.error(f"Error flushing data for a cerebro instance: {e}")

        # Cerebroのデータフィードに停止を通知
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'stop'):
                cerebro.datas[0].stop()

        # 各スレッドの終了を待つ
        if self.synchronizer.is_alive():
            self.synchronizer.join(timeout=5)
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=5)
        
        self.connector.stop()
        logger.info("RealtimeTrader stopped.")

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime', level=config.LOG_LEVEL)
    notifier.start_notifier()
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while True: time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Ctrl+C detected. Shutting down gracefully.")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred in the main thread: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
        notifier.stop_notifier()
        logger.info("Application has been shut down.")

if __name__ == '__main__':
    main()