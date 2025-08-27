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
        ('cerebro', None),
    )

    def __init__(self):
        if self.p.cerebro is None:
            raise ValueError("Cerebroインスタンスが 'cerebro' パラメータとして渡されていません。")
        self.broker = self.p.cerebro.broker

        self._hist_df = self.p.dataname
        
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
        self._historical_phase_completed = False

    def stop(self):
        self._stopevent.set()

    def _load(self):
        # --- 過去データ供給フェーズ ---
        if self._hist_df is not None and not self._hist_df.empty:
            row = self._hist_df.iloc[0]
            self._hist_df = self._hist_df.iloc[1:]
            
            self._populate_lines(row)
            # [修正] 削除されていたログ行を復活
            logger.debug(f"[{self.symbol}] 過去データを供給: {row.name}")
            return True

        # --- リアルタイムフェーズへの移行通知 ---
        if not self._historical_phase_completed:
            self._historical_phase_completed = True
            if hasattr(self.broker, 'live_data_started'):
                logger.info(f"[{self.symbol}] 過去データの供給が完了。ブローカーにリアルタイム移行を通知します。")
                self.broker.live_data_started = True
        
        # --- リアルタイムデータ供給フェーズ ---
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
        
        row = pd.Series({
            'open': data.get('open') if data.get('open') is not None else new_close,
            'high': data.get('high') if data.get('high') is not None else new_close,
            'low': data.get('low') if data.get('low') is not None else new_close,
            'close': new_close,
            'volume': data.get('volume', 0),
            'openinterest': 0
        }, name=current_dt)

        self._populate_lines(row)
        logger.debug(f"[{self.symbol}] 新規バー供給: Close={self.last_close}")
        return True

    def _load_heartbeat(self):
        if self.last_close is None:
            return None
            
        epsilon = 0.0 if self.last_close is None else self.last_close * 0.0001
        
        current_dt = datetime.now()
        row = pd.Series({
            'open': self.last_close,
            'high': self.last_close + epsilon,
            'low': self.last_close,
            'close': self.last_close,
            'volume': 0, 
            'openinterest': 0
        }, name=current_dt)
        
        self._populate_lines(row)
        logger.debug(f"[{self.symbol}] ハートビート供給: Close={self.last_close}")
        return True

    def _populate_lines(self, row):
        self.lines.datetime[0] = self.date2num(row.name)
        self.lines.open[0] = float(row['open'])
        self.lines.high[0] = float(row['high'])
        self.lines.low[0] = float(row['low'])
        self.lines.close[0] = float(row['close'])
        self.lines.volume[0] = float(row.get('volume', 0))
        self.lines.openinterest[0] = float(row.get('openinterest', 0))
        self.last_close = self.lines.close[0]
        self.last_dt = pd.to_datetime(row.name).to_pydatetime()