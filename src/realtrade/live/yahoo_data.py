import backtrader as bt; from datetime import datetime; import time; import threading; import logging; import yfinance as yf; import pandas as pd
logger = logging.getLogger(__name__)
class YahooData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1),)
    def __init__(self):
        store = self.p.store;
        if not store: raise ValueError("YahooDataにはstoreの指定が必要です。")
        symbol = self.p.dataname; df = store.get_historical_data(dataname=symbol, period='7d', interval='1m')
        if df.empty: logger.warning(f"[{symbol}] 履歴データがありません。"); df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
        self.p.dataname = df; super(YahooData, self).__init__(); self.symbol_str = symbol; self._thread = None; self._stop_event = threading.Event()
    def start(self):
        super(YahooData, self).start(); logger.info(f"[{self.symbol_str}] YahooDataスレッドを開始します..."); self._thread = threading.Thread(target=self._run, daemon=True); self._thread.start()
    def stop(self):
        logger.info(f"[{self.symbol_str}] YahooDataスレッドを停止します..."); self._stop_event.set()
        if self._thread is not None: self._thread.join()
        super(YahooData, self).stop()
    def _run(self):
        while not self._stop_event.is_set():
            try:
                time.sleep(60); ticker = f"{self.symbol_str}.T"; df = yf.download(ticker, period='1d', interval='1m', progress=False, auto_adjust=False)
                if df.empty: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]
                if df.columns.duplicated().any(): df = df.loc[:, ~df.columns.duplicated(keep='first')]
                if len(self.lines.datetime) > 0 and self.lines.datetime[-1] >= bt.date2num(df.index[-1].to_pydatetime()): continue
                latest_bar = df.iloc[-1]; self.lines.datetime[0] = bt.date2num(latest_bar.name.to_pydatetime()); self.lines.open[0] = latest_bar['Open'].item(); self.lines.high[0] = latest_bar['High'].item(); self.lines.low[0] = latest_bar['Low'].item(); self.lines.close[0] = latest_bar['Close'].item(); self.lines.volume[0] = latest_bar['Volume'].item(); self.lines.openinterest[0] = 0.0; self.put_notification(self.LIVE)
                logger.debug(f"[{self.symbol_str}] 新しいデータを追加: {latest_bar.name}")
            except Exception as e: logger.error(f"データ取得スレッドでエラーが発生: {e}"); time.sleep(60)