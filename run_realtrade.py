import logging
import time
import yaml
import pandas as pd
import glob
import os
from dotenv import load_dotenv
import backtrader as bt

# 環境変数をロード
load_dotenv()

# モジュールをインポート
import config_realtrade as config
import logger_setup
import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.analyzer import TradePersistenceAnalyzer

# --- モードに応じてインポートするモジュールを切り替え ---
if config.LIVE_TRADING:
    from realtrade.live.sbi_store import SBIStore
    from realtrade.live.sbi_broker import SBIBroker
    from realtrade.live.sbi_data import SBIData
else:
    from realtrade.mock.data_fetcher import MockDataFetcher

# ロガーのセットアップ
logger_setup.setup_logging(config, log_prefix='realtime')
logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
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
        cerebro = bt.Cerebro(runonce=False) # リアルタイムなのでrunonce=False
        
        # --- Live/Mockモードに応じてBrokerとDataFeedを設定 ---
        if config.LIVE_TRADING:
            logger.info("ライブモード用のStore, Broker, DataFeedをセットアップします。")
            store = SBIStore(
                api_key=config.API_KEY,
                api_secret=config.API_SECRET
            )
            
            # Brokerをセット
            broker = SBIBroker(store=store)
            cerebro.setbroker(broker)
            logger.info("-> SBIBrokerをCerebroにセットしました。")
            
            # データフィードをセット
            for symbol in self.symbols:
                data_feed = SBIData(dataname=symbol, store=store)
                cerebro.adddata(data_feed, name=str(symbol))
            logger.info(f"-> {len(self.symbols)}銘柄のSBIDataフィードをCerebroに追加しました。")
            
        else: # シミュレーションモード
            logger.info("シミュレーションモード用のBrokerとDataFeedをセットアップします。")
            data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
            
            # Brokerをセット (標準のBackBroker)
            broker = bt.brokers.BackBroker()
            cerebro.setbroker(broker)
            logger.info("-> 標準のBackBrokerをセットしました。")
            
            # データフィードをセット
            for symbol in self.symbols:
                data_feed = data_fetcher.get_data_feed(str(symbol))
                cerebro.adddata(data_feed, name=str(symbol))
            logger.info(f"-> {len(self.symbols)}銘柄のMockデータフィードをCerebroに追加しました。")
        
        # --- 共通のセットアップ ---
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        logger.info("-> 永続化用AnalyzerをCerebroに追加しました。")

        cerebro.addstrategy(btrader_strategy.DynamicStrategy,
                            strategy_catalog=self.strategy_catalog,
                            strategy_assignments=self.strategy_assignments)
        logger.info("-> DynamicStrategyをCerebroに追加しました。")
        
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

if __name__ == '__main__':
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