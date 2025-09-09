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

from src.core.util import logger as logger_setup, notifier
from . import config_realtrade as config
from .strategy import RealTradeStrategy

if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'RAKUTEN':
        from .bridge.excel_bridge import ExcelBridge
        from .rakuten.rakuten_data import RakutenData
        from .rakuten.rakuten_broker import RakutenBroker
else:
    pass

logger = logging.getLogger(__name__)

# [修正] threading.excepthookの仕様に合わせたカスタムハンドラ
def threading_exception_handler(args):
    exc_type = args.exc_type
    exc_value = args.exc_value
    exc_traceback = args.exc_traceback
    
    if issubclass(exc_type, KeyboardInterrupt):
        # KeyboardInterruptは通常通り扱う
        return
    logger.debug("スレッド内の未捕捉の例外:", exc_info=(exc_type, exc_value, exc_traceback))

# [修正] sys.excepthook用のカスタムハンドラ
def sys_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.debug("メインスレッドの未捕捉の例外:", exc_info=(exc_type, exc_value, exc_traceback))


class PositionSynchronizer(threading.Thread):
    def __init__(self, bridge, strategies, stop_event):
        super().__init__(daemon=True)
        self.name = "PositionSynchronizer"
        self.bridge = bridge
        self.strategies = strategies
        self.stop_event = stop_event
        logger.info("PositionSynchronizerが初期化されました。")

    def run(self):
        logger.info("ポジション同期スレッドを開始します。")
        while not self.stop_event.is_set():
            excel_positions = self.bridge.get_positions()
            internal_positions = {}
            strategies_copy = self.strategies.copy()
            for symbol, strategy in strategies_copy.items():
                if hasattr(strategy, 'live_trading_started') and strategy.live_trading_started and strategy.position:
                    internal_positions[symbol] = {
                        'size': strategy.position.size,
                        'price': strategy.position.price
                    }
            self._sync_positions(excel_positions, internal_positions)
            time.sleep(1)
        logger.info("ポジション同期スレッドが正常に停止しました。")

    def _sync_positions(self, excel_pos, internal_pos):
        all_symbols = set(excel_pos.keys()) | set(internal_pos.keys())
        for symbol in all_symbols:
            strategy = self.strategies.get(symbol)
            if not strategy or not (hasattr(strategy, 'live_trading_started') and strategy.live_trading_started):
                continue
            e_pos = excel_pos.get(symbol)
            i_pos = internal_pos.get(symbol)
            if e_pos and not i_pos:
                logger.info(f"[{symbol}] 新規ポジションを検知。内部状態に注入します。")
                strategy.inject_position(e_pos['size'], e_pos['price'])
            elif not e_pos and i_pos:
                logger.info(f"[{symbol}] 決済ポジションを検知。内部状態をクリアします。")
                strategy.force_close_position()
            elif e_pos and i_pos:
                if e_pos['size'] != i_pos['size'] or e_pos['price'] != i_pos['price']:
                    logger.info(f"[{symbol}] ポジションの差異を検知。Excelの情報に更新します。")
                    strategy.inject_position(e_pos['size'], e_pos['price'])

class RealtimeTrader:
    def __init__(self):
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.threads, self.cerebro_instances, self.strategy_instances = [], [], {}
        self.stop_event = threading.Event()
        self.synchronizer = None
        self.bridge = None
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            self.bridge = ExcelBridge(workbook_path=config.EXCEL_WORKBOOK_PATH)

    def _load_yaml(self, fp):
        with open(fp, 'r', encoding='utf-8') as f: return yaml.safe_load(f)
        
    def _load_strategy_assignments(self, pattern):
        files = glob.glob(pattern)
        if not files: raise FileNotFoundError(f"推奨戦略ファイルが見つかりません: {pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"推奨戦略ファイルを読み込みました: {latest_file}")
        df = pd.read_csv(latest_file)
        return pd.Series(df.iloc[:, 0].values, index=df.iloc[:, 1].astype(str)).to_dict()

    def _run_cerebro(self, cerebro_instance):
        cerebro_instance.run()
        logger.info(f"Cerebroスレッド ({threading.current_thread().name}) 終了。")

    def _create_cerebro_for_symbol(self, symbol):
        strategy_name = self.strategy_assignments.get(str(symbol))
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not strategy_name or not entry_strategy_def:
            logger.warning(f"銘柄 {symbol} の戦略定義が見つかりません。")
            return None
        strategy_params = copy.deepcopy(self.base_strategy_params)
        strategy_params.update(entry_strategy_def)
        cerebro = bt.Cerebro(runonce=False)
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if not self.bridge: return None
            cerebro.setbroker(RakutenBroker(bridge=self.bridge))
            cerebro.broker.set_cash(10**12)
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
                except Exception: pass
            primary_data = RakutenData(dataname=hist_df, bridge=self.bridge, symbol=symbol,
                timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']), compression=short_tf_config['compression'])
            cerebro.adddata(primary_data, name=str(symbol))
            for tf_name in ['medium', 'long']:
                if tf_config := strategy_params['timeframes'].get(tf_name):
                    cerebro.resampledata(primary_data, timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                                         compression=tf_config['compression'], name=tf_name)
        else: return None
        cerebro.addstrategy(RealTradeStrategy, strategy_params=strategy_params, strategy_components={})
        self.strategy_instances[str(symbol)] = cerebro.strats[0][0]
        return cerebro

    def start(self):
        if self.bridge: self.bridge.start()
        for symbol in self.symbols:
            if cerebro := self._create_cerebro_for_symbol(symbol):
                self.cerebro_instances.append(cerebro)
                t = threading.Thread(target=self._run_cerebro, args=(cerebro,), name=f"Cerebro-{symbol}", daemon=True)
                self.threads.append(t); t.start()
        self.synchronizer = PositionSynchronizer(bridge=self.bridge, strategies=self.strategy_instances, stop_event=self.stop_event)
        self.synchronizer.start()

    def stop(self):
        self.stop_event.set()
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'stop'):
                cerebro.datas[0].stop()
        if self.bridge: self.bridge.stop()
        if self.synchronizer: self.synchronizer.join(timeout=5)

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime', level=config.LOG_LEVEL)
    
    # [修正] 正しいシグネチャを持つハンドラを設定
    sys.excepthook = sys_exception_handler
    threading.excepthook = threading_exception_handler
    
    notifier.start_notifier()
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while True: time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Ctrl+C検知。システムを安全に停止します。")
    finally:
        if trader: trader.stop()
        notifier.stop_notifier()
        logger.info("メインスレッドが終了しました。")

if __name__ == '__main__':
    main()