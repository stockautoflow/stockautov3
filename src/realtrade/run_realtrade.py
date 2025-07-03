import logging
import time
import yaml
import pandas as pd
import glob
import os
import sys
import backtrader as bt

# [リファクタリング] パス解決のための処理
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# [リファクタリング] 新しいパッケージ構造に合わせてインポートを変更
from src.core.util import logger as logger_setup
from src.core import strategy as btrader_strategy
from . import config_realtrade as config
from .state_manager import StateManager
from .analyzer import TradePersistenceAnalyzer

# --- モードに応じてインポートするモジュールを切り替え ---
if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'SBI':
        from .live.sbi_store import SBIStore as LiveStore
        from .live.sbi_broker import SBIBroker as LiveBroker
        from .live.sbi_data import SBIData as LiveData
    elif config.DATA_SOURCE == 'YAHOO':
        from .live.yahoo_store import YahooStore as LiveStore
        from backtrader.brokers import BackBroker as LiveBroker
        from .live.yahoo_data import YahooData as LiveData
    else:
        raise ValueError(f"サポートされていないDATA_SOURCEです: {config.DATA_SOURCE}")
else:
    from .mock.data_fetcher import MockDataFetcher

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_strategy_catalog(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.symbols = [s for s in self.symbols if s and str(s).lower() != 'nan']
        self.state_manager = StateManager(config.DB_PATH)
        
        self.cerebro = self._setup_cerebro()
        self.is_running = False

    def _load_strategy_catalog(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return {s['name']: s for s in yaml.safe_load(f)}
        except FileNotFoundError:
            logger.error(f"戦略カタログファイル '{filepath}' が見つかりません。")
            raise

    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files:
            raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"最新の対応ファイルをロード: {latest_file}")
        df = pd.read_csv(latest_file)
        strategy_col, symbol_col = df.columns[0], df.columns[1]
        return pd.Series(df[strategy_col].values, index=df[symbol_col].astype(str)).to_dict()

    def _setup_cerebro(self):
        logger.info("Cerebroエンジンをセットアップ中...")
        cerebro = bt.Cerebro(runonce=False)
        
        if config.LIVE_TRADING:
            logger.info(f"ライブモード({config.DATA_SOURCE})用のStore, Broker, DataFeedをセットアップします。")
            store = LiveStore(api_key=config.API_KEY, api_secret=config.API_SECRET) if config.DATA_SOURCE == 'SBI' else LiveStore()
            broker = LiveBroker(store=store) if config.DATA_SOURCE == 'SBI' else LiveBroker()
            cerebro.setbroker(broker)
            logger.info(f"-> {broker.__class__.__name__}をCerebroにセットしました。")
            for symbol in self.symbols:
                # [修正] ライブモードでも3つのデータフィードを追加する必要があるが、
                #        現状のLiveDataは1つしか返さないため、暫定的に同じものを3つ追加する。
                #        TODO: LiveDataが複数タイムフレームを返せるように改修が必要。
                data_feed = LiveData(dataname=symbol, store=store)
                cerebro.adddata(data_feed, name=str(symbol))
                cerebro.adddata(LiveData(dataname=symbol, store=store), name=str(symbol))
                cerebro.adddata(LiveData(dataname=symbol, store=store), name=str(symbol))
            logger.info(f"-> {len(self.symbols)}銘柄の{LiveData.__name__}フィード(3階層)をCerebroに追加しました。")
        else:
            logger.info("シミュレーションモード用のBrokerとDataFeedをセットアップします。")
            data_fetcher = MockDataFetcher(symbols=self.symbols)
            broker = bt.brokers.BackBroker()
            cerebro.setbroker(broker)
            logger.info("-> 標準のBackBrokerをセットしました。")
            
            # [修正] シミュレーションモードで、戦略が必要とする3つのデータフィードを追加する
            # ポートフォリオ実行ではなく、単一銘柄でのロジックテストとして動作させる
            if self.symbols:
                target_symbol = self.symbols[0]
                logger.info(f"シミュレーションは最初の銘柄 ({target_symbol}) のみで実行します。")
                
                # 同じダミーデータを3つ追加して、short, medium, longの要件を満たす
                cerebro.adddata(data_fetcher.get_data_feed(str(target_symbol)), name=str(target_symbol))
                cerebro.adddata(data_fetcher.get_data_feed(str(target_symbol)), name=str(target_symbol))
                cerebro.adddata(data_fetcher.get_data_feed(str(target_symbol)), name=str(target_symbol))
                
                logger.info(f"-> 銘柄 {target_symbol} のMockデータフィード(3階層)をCerebroに追加しました。")
            else:
                logger.warning("取引対象の銘柄が見つかりません。")

        
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        logger.info("-> 永続化用AnalyzerをCerebroに追加しました。")

        cerebro.addstrategy(btrader_strategy.DynamicStrategy,
                            strategy_catalog=self.strategy_catalog,
                            strategy_assignments=self.strategy_assignments,
                            live_trading=config.LIVE_TRADING)
        logger.info(f"-> DynamicStrategyをCerebroに追加しました (live_trading={config.LIVE_TRADING})。")
        
        logger.info("Cerebroエンジンのセットアップが完了しました。")
        return cerebro

    def start(self):
        logger.info("システムを開始します。")
        self.is_running = True
        self.cerebro.run()
        logger.info("Cerebroの実行が完了しました。")
        self.is_running = False

    def stop(self):
        logger.info("システムを停止します。")
        self.is_running = False
        if self.state_manager:
            self.state_manager.close()
        logger.info("システムが正常に停止しました。")

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime')
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
    except KeyboardInterrupt:
        logger.info("\nCtrl+Cを検知しました。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
    logger.info("--- リアルタイムトレードシステム終了 ---")

if __name__ == '__main__':
    main()