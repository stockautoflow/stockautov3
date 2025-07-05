import backtrader as bt; from datetime import datetime; import time; import threading; import logging; import yfinance as yf; import pandas as pd
logger = logging.getLogger(__name__)
class YahooData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1), ('drop_newest', True),)
    
    def __init__(self):
        store = self.p.store
        if not store: raise ValueError("YahooDataにはstoreの指定が必要です。")
        symbol = self.p.dataname
        interval_map = {(bt.TimeFrame.Days, 1): '1d', (bt.TimeFrame.Minutes, 60): '60m', (bt.TimeFrame.Minutes, 1): '1m'}
        interval = interval_map.get((self.p.timeframe, self.p.compression), '1m')
        period = '7d' if interval == '1m' else '2y'
        df = store.get_historical_data(dataname=symbol, period=period, interval=interval)
        if df.empty:
            logger.warning(f"[{symbol}] 履歴データがありません。")
            df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
        if self.p.drop_newest and not df.empty: df = df.iloc[:-1]
        self.p.dataname = df
        super(YahooData, self).__init__()
        self.symbol_str = symbol
        self._thread = None
        self._stop_event = threading.Event()
        self.last_dt = df.index[-1].to_pydatetime() if not df.empty else None

    def start(self):
        super(YahooData, self).start()
        logger.info(f"[{self.symbol_str}] YahooDataスレッドを開始します...")
        self._thread = threading.Thread(target=self._run, daemon=False)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.symbol_str}] YahooDataスレッドを停止します...")
        self._stop_event.set()
        if self._thread is not None: self._thread.join()
        super(YahooData, self).stop()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                ticker = f"{self.symbol_str}.T"
                df = yf.download(ticker, period='2d', interval='1m', progress=False, auto_adjust=False)
                new_data_pushed = False
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.columns = [x.lower() for x in df.columns]
                    if df.index.tz is not None: df.index = df.index.tz_localize(None)
                    latest_bar_dt = df.index[-1].to_pydatetime()
                    if self.last_dt is None or latest_bar_dt > self.last_dt:
                        latest_bar = df.iloc[-1]
                        self.lines.datetime[0] = bt.date2num(latest_bar.name)
                        self.lines.open[0], self.lines.high[0], self.lines.low[0], self.lines.close[0], self.lines.volume[0] = latest_bar['open'], latest_bar['high'], latest_bar['low'], latest_bar['close'], latest_bar['volume']
                        self.lines.openinterest[0] = 0.0
                        self.put_notification(self.LIVE)
                        self.last_dt = latest_bar_dt
                        new_data_pushed = True
                        logger.debug(f"[{self.symbol_str}] 新しいデータを追加: {latest_bar.name}")
                if not new_data_pushed: self._put_heartbeat()
                time.sleep(60)
            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}")
                time.sleep(60)
    
    def _put_heartbeat(self):
        if len(self) > 0:
            self.lines.datetime[0] = bt.date2num(datetime.now())
            self.lines.open[0] = self.lines.close[-1]
            self.lines.high[0] = self.lines.close[-1]
            self.lines.low[0] = self.lines.close[-1]
            self.lines.close[0] = self.lines.close[-1]
            self.lines.volume[0], self.lines.openinterest[0] = 0, 0
            self.put_notification(self.LIVE)
            logger.debug(f"[{self.symbol_str}] データ更新なし、ハートビートを供給。")