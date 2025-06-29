import backtrader as bt
import pandas as pd
from datetime import datetime
import time
import threading
import random
import logging

logger = logging.getLogger(__name__)

class SBIData(bt.feeds.PandasData):
    """
    SBIStore経由でリアルタイムデータを取得し、Cerebroに供給するデータフィード。
    """
    params = (
        ('store', None),
        ('timeframe', bt.TimeFrame.Minutes),
        ('compression', 1),
    )

    def __init__(self, **kwargs):
        super(SBIData, self).__init__(**kwargs)
        if not self.p.store:
            raise ValueError("SBIDataにはstoreの指定が必要です。")
        self.store = self.p.store
        self._thread = None
        self._stop_event = threading.Event()
        
        # 履歴データを取得して初期化
        self.init_data = self.store.get_historical_data(
            self.p.dataname, self.p.timeframe, self.p.compression, 200
        )

    def start(self):
        super(SBIData, self).start()
        if self.init_data is not None and not self.init_data.empty:
            logger.info(f"[{self.p.dataname}] 履歴データをロードします。")
            self.add_history(self.init_data)
        
        logger.info(f"[{self.p.dataname}] リアルタイムデータ取得スレッドを開始します...")
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.p.dataname}] リアルタイムデータ取得スレッドを停止します...")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        super(SBIData, self).stop()

    def _run(self):
        """バックグラウンドで価格データを生成/取得し続ける"""
        while not self._stop_event.is_set():
            try:
                # 本来はここでWebSocketやAPIポーリングを行う
                # --- ここから下はダミーデータ生成ロジック ---
                time.sleep(5) # 5秒ごとに更新をシミュレート
                
                # 直前の足のデータを取得
                last_close = self.close[-1] if len(self.close) > 0 else 1000
                
                # 新しい足のデータを生成
                new_open = self.open[0] = self.close[0] if len(self.open) > 0 else last_close
                change = random.uniform(-0.005, 0.005)
                new_close = new_open * (1 + change)
                new_high = max(new_open, new_close) * (1 + random.uniform(0, 0.002))
                new_low = min(new_open, new_close) * (1 - random.uniform(0, 0.002))
                new_volume = random.randint(100, 5000)

                # backtraderにデータをセット
                self.lines.datetime[0] = bt.date2num(datetime.now())
                self.lines.open[0] = new_open
                self.lines.high[0] = new_high
                self.lines.low[0] = new_low
                self.lines.close[0] = new_close
                self.lines.volume[0] = new_volume
                
                self.put_notification(self.LIVE) # データ更新をCerebroに通知
                # --- ダミーデータ生成ロジックここまで ---

            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}")
                time.sleep(10) # エラー発生時は少し待つ

    def add_history(self, df):
        """履歴データをデータフィードにロードする"""
        if df is None or df.empty: return
        
        for index, row in df.iterrows():
            self.lines.datetime[0] = bt.date2num(index.to_pydatetime())
            self.lines.open[0] = row['open']
            self.lines.high[0] = row['high']
            self.lines.low[0] = row['low']
            self.lines.close[0] = row['close']
            self.lines.volume[0] = row['volume']
            self.put_notification(self.DELAYED)