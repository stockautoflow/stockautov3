import logging
import time
import yaml
import pandas as pd
import glob
import os
from dotenv import load_dotenv
import backtrader as bt

load_dotenv()

import config_realtrade as config
import logger_setup
import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.mock.data_fetcher import MockDataFetcher
from realtrade.analyzer import TradePersistenceAnalyzer

logger_setup.setup_logging(config, log_prefix='realtime')
logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        if not config.API_KEY or not config.API_SECRET:
            logger.error("APIキーまたはシークレットが設定されていません。")
            raise ValueError("APIキーが設定されていません。")
        self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        logger.info(f"ロードした戦略カタログ: {list(self.strategy_catalog.keys())}")
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        logger.info(f"ロードした銘柄・戦略の割り当て: {self.strategy_assignments}")
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(config.DB_PATH)
        
        self.data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
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
        logger.info(f"CSVから読み込んだ列: 戦略='{strategy_col}', 銘柄='{symbol_col}'")
        return pd.Series(df[strategy_col].values, index=df[symbol_col].astype(str)).to_dict()

    def _setup_cerebro(self):
        logger.info("Cerebroエンジンをセットアップ中...")
        cerebro = bt.Cerebro(runonce=False)
        
        broker = bt.brokers.BackBroker()
        cerebro.setbroker(broker)
        logger.info("-> 標準のBackBrokerをセットしました。")

        for symbol in self.symbols:
            data_feed = self.data_fetcher.get_data_feed(str(symbol))
            if data_feed is not None:
                cerebro.adddata(data_feed, name=str(symbol))
            else:
                logger.warning(f"銘柄 {symbol} のデータフィードを取得できませんでした。スキップします。")
        
        logger.info(f"-> {len(self.symbols)}銘柄のデータフィードをCerebroに追加しました。")
        
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
        self.data_fetcher.start()
        logger.info("ドライランを開始します... (実際の注文は行われません)")
        self.is_running = True
        self.cerebro.run()
        logger.info("ドライランが完了しました。")
        self.is_running = False

    def stop(self):
        logger.info("システムを停止します。")
        self.is_running = False
        if hasattr(self, 'data_fetcher'): self.data_fetcher.stop()
        if hasattr(self, 'state_manager'): self.state_manager.close()
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