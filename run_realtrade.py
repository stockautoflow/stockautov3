import logging
import schedule
import time
import yaml
import pandas as pd
import glob
from datetime import datetime
import os
from dotenv import load_dotenv
import backtrader as bt

# .envファイルから環境変数をロード
load_dotenv()

import config_realtrade as config
# import logger_setup
import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.mock.broker import MockBrokerBridge
from realtrade.mock.data_fetcher import MockDataFetcher

# logger_setup.setup_logging()
# logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        print("リアルタイムトレーダーを初期化中...")
        if not config.API_KEY or not config.API_SECRET:
            print("エラー: APIキーまたはシークレットが設定されていません。")
            raise ValueError("APIキーが設定されていません。")

        # 戦略カタログと銘柄リストの読み込み
        self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        print(f"-> ロードした戦略カタログ: {list(self.strategy_catalog.keys())}")
        
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        print(f"-> ロードした銘柄・戦略の割り当て: {self.strategy_assignments}")
        
        self.symbols = list(self.strategy_assignments.keys())
        
        # 各モジュールの初期化
        self.state_manager = StateManager(config.DB_PATH)
        self.broker = MockBrokerBridge(config=config)
        self.data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
        
        # [実装] Cerebroエンジンをセットアップ
        self.cerebro = self._setup_cerebro()
        self.is_running = False

    def _load_strategy_catalog(self, filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            strategies = yaml.safe_load(f)
        return {s['name']: s for s in strategies}

    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files:
            raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        print(f"-> 最新の対応ファイルをロード: {latest_file}")
        df = pd.read_csv(latest_file)
        
        strategy_col_name = df.columns[0]
        symbol_col_name = df.columns[1]
        
        print(f"-> CSVから読み込んだ列: 戦略='{strategy_col_name}', 銘柄='{symbol_col_name}'")

        return pd.Series(df[strategy_col_name].values, index=df[symbol_col_name].astype(str)).to_dict()

    def _setup_cerebro(self):
        """backtraderのCerebroエンジンをセットアップします。"""
        print("\nCerebroエンジンをセットアップ中...")
        cerebro = bt.Cerebro(runonce=False) # リアルタイムなのでrunonce=False

        # 1. Brokerをセット
        cerebro.setbroker(self.broker)
        print("-> BrokerをCerebroにセットしました。")

        # 2. 全ての対象銘柄のデータフィードを追加
        for symbol in self.symbols:
            data_feed = self.data_fetcher.get_data_feed(str(symbol))
            cerebro.adddata(data_feed, name=str(symbol))
        print(f"-> {len(self.symbols)}銘柄のデータフィードをCerebroに追加しました。")

        # 3. 戦略クラスにカタログと対応表を渡して追加
        cerebro.addstrategy(
            btrader_strategy.DynamicStrategy,
            strategy_catalog=self.strategy_catalog,
            strategy_assignments=self.strategy_assignments
        )
        print("-> DynamicStrategyをCerebroに追加しました。")
        
        print("Cerebroエンジンのセットアップが完了しました。")
        return cerebro


    def start(self):
        print("\nシステムを開始します。")
        self.broker.start()
        self.data_fetcher.start()
        print(f"-> Cerebroインスタンスの準備完了: {self.cerebro}")
        self.is_running = True
        print("\nシステムは起動状態です。Ctrl+Cで終了します。")

    def stop(self):
        print("\nシステムを停止します。")
        if hasattr(self, 'broker'): self.broker.stop()
        if hasattr(self, 'data_fetcher'): self.data_fetcher.stop()
        if hasattr(self, 'state_manager'): self.state_manager.close()
        self.is_running = False
        print("システムが正常に停止しました。")

if __name__ == '__main__':
    print("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCtrl+Cを検知しました。")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
    finally:
        if trader:
            trader.stop()