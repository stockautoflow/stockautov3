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

        # モック用のダミー銘柄リスト
        self.symbols = [1301, 7203] 
        print(f"対象銘柄: {self.symbols}")

        # 各モジュールの初期化
        self.state_manager = StateManager(config.DB_PATH)
        self.broker = MockBrokerBridge(config=config)
        self.data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
        
        # self.cerebro = self._setup_cerebro()
        self.is_running = False

    def _test_state_manager(self):
        """StateManagerの動作を確認するためのテストメソッド。"""
        print("\n--- StateManagerテスト開始 ---")
        try:
            # ポジションのテスト
            print("1. ポジション情報を保存します...")
            dt_now = datetime.now().isoformat()
            self.state_manager.save_position('1301', 100, 2500.5, dt_now)
            self.state_manager.save_position('7203', -50, 8800.0, dt_now)
            
            print("2. ポジション情報を読み込みます...")
            positions = self.state_manager.load_positions()
            print("読み込んだポジション:", positions)
            assert len(positions) == 2
            assert positions['1301']['size'] == 100

            # 注文のテスト
            print("3. 注文情報を保存します...")
            self.state_manager.save_order('order-001', '1301', 'buy_limit', 100, 2400.0, 'submitted')
            
            print("4. 注文情報を更新します...")
            self.state_manager.update_order_status('order-001', 'accepted')

            print("5. 注文情報を読み込みます...")
            orders = self.state_manager.load_orders()
            print("読み込んだ注文:", orders)
            assert orders['order-001']['status'] == 'accepted'

            print("6. ポジションを削除します...")
            self.state_manager.delete_position('7203')
            positions = self.state_manager.load_positions()
            print("削除後のポジション:", positions)
            assert '7203' not in positions
            
            print("--- StateManagerテスト正常終了 ---")
        except Exception as e:
            print(f"--- StateManagerテスト中にエラーが発生しました: {e} ---")


    def start(self):
        print("システムを開始します。")
        self.broker.start()
        self.data_fetcher.start()

        # 動作確認
        self._test_state_manager()

        self.is_running = True
        print("\nシステムは起動状態です。Ctrl+Cで終了します。")


    def stop(self):
        print("システムを停止します。")
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