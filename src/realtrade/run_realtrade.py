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
        self.cerebro_instances = [] # Cerebroインスタンスを保持

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
                self.cerebro_instances.append(cerebro_instance)
                t = threading.Thread(target=self._run_cerebro, args=(cerebro_instance,), name=f"Cerebro-{symbol}", daemon=False)
                self.threads.append(t)
                t.start()
                logger.info(f"Cerebroスレッド (Cerebro-{symbol}) を開始しました。")

    def stop(self):
        logger.info("システムを停止します。全データフィードに停止信号を送信...")
        for cerebro in self.cerebro_instances:
            if cerebro.datas and len(cerebro.datas) > 0 and hasattr(cerebro.datas[0], 'stop'):
                try:
                    cerebro.datas[0].stop()
                except Exception as e:
                    logger.error(f"データフィードの停止中にエラー: {e}")

        logger.info("全Cerebroスレッドの終了を待機中...")
        for t in self.threads:
            t.join(timeout=10)
        if self.state_manager: self.state_manager.close()
        logger.info("システムが正常に停止しました。")

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime')
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        
        # 能動的な監視ループ
        while True:
            # 稼働中のスレッドがなくなったらループを抜ける
            if not trader.threads or not any(t.is_alive() for t in trader.threads):
                logger.warning("稼働中の取引スレッドがありません。システムを終了します。")
                break
            time.sleep(5)  # 5秒ごとにスレッドの生存を確認

    except KeyboardInterrupt:
        logger.info("\nCtrl+Cを検知しました。システムを優雅に停止します。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
    logger.info("--- リアルタイムトレードシステム終了 ---")

if __name__ == '__main__':
    main()