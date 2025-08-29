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
from src.core.util import notifier
from src.core import strategy as btrader_strategy
from src.core.data_preparer import prepare_data_feeds
from . import config_realtrade as config
from .state_manager import StateManager
from .analyzer import TradePersistenceAnalyzer

if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'YAHOO':
        from .live.yahoo_store import YahooStore as LiveStore
    elif config.DATA_SOURCE == 'RAKUTEN':
        from .bridge.excel_bridge import ExcelBridge
        from .rakuten.rakuten_data import RakutenData
        from .rakuten.rakuten_broker import RakutenBroker
    else:
        raise ValueError(f"サポートされていないDATA_SOURCEです: {config.DATA_SOURCE}")
else:
    from .mock.data_fetcher import MockDataFetcher

class NoCreditInterest(bt.CommInfoBase):
    def get_credit_interest(self, data, pos, dt):
        return 0.0

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(os.path.join(config.BASE_DIR, "results", "realtrade", "realtrade_state.db"))
        
        self.persisted_positions = self.state_manager.load_positions()
        if self.persisted_positions:
            logger.info(f"DBから{len(self.persisted_positions)}件の既存ポジションを検出しました。")

        self.threads = []
        self.cerebro_instances = []
        
        self.bridge = None
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if self.bridge is None:
                logger.info("楽天証券(Excelハブ)モードで初期化します。")
                self.bridge = ExcelBridge(workbook_path=config.EXCEL_WORKBOOK_PATH)
                self.bridge.start()

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
        cerebro = bt.Cerebro(runonce=False)
        
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if not self.bridge:
                logger.error("ExcelBridgeが初期化されていません。")
                return None
            
            cerebro.setbroker(RakutenBroker(bridge=self.bridge))
            cerebro.broker.set_cash(100_000_000_000)
            cerebro.broker.addcommissioninfo(NoCreditInterest())

            short_tf_config = strategy_params['timeframes']['short']
            compression = short_tf_config['compression']
            search_pattern = os.path.join(config.DATA_DIR, f"{symbol}_{compression}m_*.csv")
            files = glob.glob(search_pattern)

            hist_df = pd.DataFrame()
            if files:
                latest_file = max(files, key=os.path.getctime)
                try:
                    df = pd.read_csv(latest_file, index_col='datetime', parse_dates=True)
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    df.columns = [x.lower() for x in df.columns]
                    hist_df = df
                    logger.info(f"[{symbol}] 過去データとして '{os.path.basename(latest_file)}' ({len(hist_df)}件) を読み込みました。")
                except Exception as e:
                    logger.error(f"[{symbol}] 過去データCSVの読み込みに失敗: {e}")
            else:
                logger.warning(f"[{symbol}] 過去データCSVが見つかりません (パターン: {search_pattern})。リアルタイムデータのみで開始します。")

            primary_data = RakutenData(
                dataname=hist_df,
                bridge=self.bridge,
                symbol=symbol,
                timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
                compression=short_tf_config['compression']
            )
            
            cerebro.adddata(primary_data, name=str(symbol))
            logger.info(f"[{symbol}] RakutenData (短期) を追加しました。")

            for tf_name in ['medium', 'long']:
                tf_config = strategy_params['timeframes'].get(tf_name)
                if tf_config:
                    cerebro.resampledata(
                        primary_data,
                        timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                        compression=tf_config['compression'],
                        name=tf_name
                    )
                    logger.info(f"[{symbol}] {tf_name}データをリサンプリングで追加しました。")
        else:
            store = LiveStore() if config.LIVE_TRADING and config.DATA_SOURCE == 'YAHOO' else None
            cerebro.setbroker(bt.brokers.BackBroker())
            cerebro.broker.set_cash(config.INITIAL_CAPITAL)
            cerebro.broker.addcommissioninfo(NoCreditInterest())
            
            success = prepare_data_feeds(cerebro, strategy_params, symbol, config.DATA_DIR,
                                         is_live=config.LIVE_TRADING, live_store=store)
            if not success:
                return None

        symbol_str = str(symbol)
        persisted_position = self.persisted_positions.get(symbol_str)
        if persisted_position:
            logger.info(f"[{symbol_str}] の既存ポジション情報を戦略に渡します: {persisted_position}")

        cerebro.addstrategy(btrader_strategy.DynamicStrategy,
                            strategy_params=strategy_params,
                            live_trading=config.LIVE_TRADING,
                            persisted_position=persisted_position,
                            strategy_assignments=self.strategy_assignments,
                            strategy_catalog=self.strategy_catalog)
        
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        return cerebro

    def start(self):
        logger.info("システムを開始します。")
        if self.bridge:
            self.bridge.start()
            
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
        
        if self.bridge:
            self.bridge.stop()

        logger.info("全Cerebroスレッドの終了を待機中...")
        for t in self.threads:
            t.join(timeout=10)
        if self.state_manager: self.state_manager.close()
        logger.info("システムが正常に停止しました。")

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime', level=config.LOG_LEVEL)
    notifier.start_notifier()
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        
        while True:
            if not trader.threads or not any(t.is_alive() for t in trader.threads):
                logger.warning("稼働中の取引スレッドがありません。システムを終了します。")
                break
            time.sleep(5)

    except KeyboardInterrupt:
        logger.info("\nCtrl+Cを検知しました。システムを優雅に停止します。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
        notifier.stop_notifier()
    logger.info("--- リアルタイムトレードシステム終了 ---")

if __name__ == '__main__':
    main()