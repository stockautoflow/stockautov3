import logging
import schedule
import time
import yaml
import pandas as pd
import glob
from datetime import datetime
import os
from dotenv import load_dotenv

# --- .envファイルから環境変数をロード ---
load_dotenv()

import config_realtrade as config
# import logger_setup
# import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.mock.broker import MockBrokerBridge # [変更] モックをインポート
from realtrade.mock.data_fetcher import MockDataFetcher # [変更] モックをインポート

# logger_setup.setup_logging()
# logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        print("リアルタイムトレーダーを初期化中...")
        if not config.API_KEY or not config.API_SECRET:
            print("エラー: APIキーまたはシークレットが設定されていません。")
            raise ValueError("APIキーが設定されていません。")

        # 戦略・銘柄リストの読み込み
        # self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        # self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        # symbols = list(self.strategy_assignments.keys())

        # モック用のダミー銘柄リスト
        symbols = [1301, 7203] 
        print(f"対象銘柄: {symbols}")

        # 各モジュールの初期化
        self.state_manager = StateManager(config.DB_PATH)
        self.broker = MockBrokerBridge(config=config)
        self.data_fetcher = MockDataFetcher(symbols=symbols, config=config)
        
        # self.cerebro = self._setup_cerebro()
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
        df = pd.read_csv(latest_file)
        return pd.Series(df.strategy_name.values, index=df.symbol).to_dict()

    def start(self):
        print("システムを開始します。")
        self.broker.start()
        self.data_fetcher.start()

        # 動作確認: 現金残高を取得して表示
        cash = self.broker.get_cash()
        print(f"ブローカーから取得した現金残高: ¥{cash:,.0f}")
        
        # 動作確認: 履歴データを取得して表示
        hist_data = self.data_fetcher.fetch_historical_data(1301, 'minutes', 5, 10)
        print("データ取得モジュールから取得した履歴データ (先頭5行):")
        print(hist_data.head())

        self.is_running = True
        print("システムは起動状態です。Ctrl+Cで終了します。")


    def stop(self):
        print("システムを停止します。")
        self.broker.stop()
        self.data_fetcher.stop()
        self.state_manager.close()
        self.is_running = False
        print("システムが正常に停止しました。")

if __name__ == '__main__':
    print("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while True:
            # ここにメインループの処理（注文状態のポーリングなど）が入る
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCtrl+Cを検知しました。システムを安全に停止します...")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
    finally:
        if trader:
            trader.stop()