import backtrader as bt; import pandas as pd; from datetime import datetime; import time; import threading; import random; import logging
logger = logging.getLogger(__name__)
class SBIData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1),)
    def __init__(self):
        store = self.p.store;
        if not store: raise ValueError("SBIDataにはstoreの指定が必要です。")
        symbol = self.p.dataname; df = store.get_historical_data(dataname=symbol, timeframe=self.p.timeframe, compression=self.p.compression, period=200)
        if df is None or df.empty: logger.warning(f"[{symbol}] 履歴データがありません。"); df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
        self.p.dataname = df; super(SBIData, self).__init__(); self.symbol_str = symbol; self._thread = None; self._stop_event = threading.Event()
    def start(self):
        super(SBIData, self).start(); logger.info(f"[{self.symbol_str}] SBIDataスレッドを開始します..."); self._thread = threading.Thread(target=self._run); self._thread.start()
    def stop(self):
        logger.info(f"[{self.symbol_str}] SBIDataスレッドを停止します..."); self._stop_event.set();
        if self._thread is not None: self._thread.join()
        super(SBIData, self).stop()
    def _run(self):
        while not self._stop_event.is_set():
            try:
                time.sleep(5); last_close = self.close[-1] if len(self.close) > 0 else 1000; new_open = self.open[0] = self.close[0] if len(self.open) > 0 else last_close; new_close = new_open * (1 + random.uniform(-0.005, 0.005))
                self.lines.datetime[0] = bt.date2num(datetime.now()); self.lines.open[0] = new_open; self.lines.high[0] = max(new_open, new_close) * (1 + random.uniform(0, 0.002)); self.lines.low[0] = min(new_open, new_close) * (1 - random.uniform(0, 0.002)); self.lines.close[0] = new_close; self.lines.volume[0] = random.randint(100, 5000); self.put_notification(self.LIVE)
            except Exception as e: logger.error(f"データ取得スレッドでエラーが発生: {e}"); time.sleep(10)