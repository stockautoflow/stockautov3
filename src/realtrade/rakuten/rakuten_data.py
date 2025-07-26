import backtrader as bt
from datetime import datetime, timedelta
import logging
import pandas as pd
import threading

logger = logging.getLogger(__name__)

class RakutenData(bt.feeds.PandasData):
    
    params = (
        ('bridge', None),
        ('symbol', None),
        ('timeframe', bt.TimeFrame.Minutes),
        ('heartbeat', 1.0),
    )

    def __init__(self):
        if self.p.dataname is None:
            empty_df = pd.DataFrame(
                columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']
            )
            empty_df = empty_df.set_index('datetime')
            self.p.dataname = empty_df
        
        super(RakutenData, self).__init__()
        
        if self.p.bridge is None:
            raise ValueError("ExcelBridgeインスタンスが 'bridge' パラメータとして渡されていません。")
        if self.p.symbol is None:
            raise ValueError("銘柄コードが 'symbol' パラメータとして渡されていません。")
            
        self.bridge = self.p.bridge
        self.symbol = str(self.p.symbol)
        
        self.last_close = None
        self.last_dt = None
        self._stopevent = threading.Event()

    def stop(self):
        self._stopevent.set()

    def _load(self):
        if self._stopevent.is_set():
            return False

        current_dt = datetime.now()

        if self.last_dt and (current_dt - self.last_dt) < timedelta(seconds=self.p.heartbeat):
            return None
        
        latest_data = self.bridge.get_latest_data(self.symbol)

        if not latest_data or latest_data.get('close') is None or latest_data.get('close') == self.last_close:
            return self._load_heartbeat()

        return self._load_new_bar(latest_data)

    def _load_new_bar(self, data):
        current_dt = datetime.now()
        
        new_close = data['close']
        
        # Excel側でOHLがNoneの場合、Closeで代用
        row = pd.Series({
            'open': data.get('open') if data.get('open') is not None else new_close,
            'high': data.get('high') if data.get('high') is not None else new_close,
            'low': data.get('low') if data.get('low') is not None else new_close,
            'close': new_close,
            'volume': data.get('volume', 0),
            'openinterest': 0
        }, name=current_dt)

        self._populate_lines(row)
        self.last_close = self.lines.close[0]
        self.last_dt = current_dt
        
        logger.debug(f"[{self.symbol}] 新規バー供給: Close={self.last_close}")
        return True

    def _load_heartbeat(self):
        if self.last_close is None:
            return None

        # ▼▼▼【最終修正】▼▼▼
        # highとlowが同じ値にならないよう、微小な値を加算して値幅ゼロのデータを防ぐ
        epsilon = self.last_close * 0.0001
        
        current_dt = datetime.now()
        row = pd.Series({
            'open': self.last_close,
            'high': self.last_close + epsilon, # 微小値を加算
            'low': self.last_close,
            'close': self.last_close,
            'volume': 0, 
            'openinterest': 0
        }, name=current_dt)
        # ▲▲▲ 修正ここまで ▲▲▲
        
        self._populate_lines(row)
        self.last_dt = current_dt

        logger.debug(f"[{self.symbol}] ハートビート供給: Close={self.last_close}")
        return True

    def _populate_lines(self, row):
        self.lines.datetime[0] = self.date2num(row.name)
        self.lines.open[0] = row['open']
        self.lines.high[0] = row['high']
        self.lines.low[0] = row['low']
        self.lines.close[0] = row['close']
        self.lines.volume[0] = row['volume']
        self.lines.openinterest[0] = row['openinterest']