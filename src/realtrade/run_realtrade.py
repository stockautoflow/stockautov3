import logging, time, yaml, pandas as pd, glob, os, sys, backtrader as bt, threading, copy

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
    main()