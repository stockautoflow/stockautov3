import backtrader as bt
from datetime import datetime, timedelta, time
import logging
import pandas as pd
import threading

# [新規] BarBuilderをインポート
from ..bar_builder import BarBuilder

logger = logging.getLogger(__name__)

class RakutenData(bt.feeds.PandasData):
    
    params = (
        ('bridge', None),
        ('symbol', None),
        ('timeframe', bt.TimeFrame.Minutes),
        ('heartbeat', 1.0),
    )

    def __init__(self):
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
        
        self.last_dt = None
        self._stopevent = threading.Event()
        
        # [新規] BarBuilderのインスタンスを生成
        self.builder = BarBuilder(interval_minutes=self.p.compression)

        self.history_supplied = False if (self._hist_df is not None and not self._hist_df.empty) else True

    def stop(self):
        self._stopevent.set()

    def _load(self):
        if self._hist_df is not None and not self._hist_df.empty:
            row = self._hist_df.iloc[0]
            self._hist_df = self._hist_df.iloc[1:]
            self._populate_lines_from_series(row)
            logger.debug(f"[{self.symbol}] 過去データを供給: {row.name}")
            if self._hist_df.empty:
                self.history_supplied = True
            return True

        if self._stopevent.is_set():
            return False

        current_dt = datetime.now()
        if self.last_dt and (current_dt - self.last_dt) < timedelta(seconds=self.p.heartbeat):
            return None
        
        # [修正] ここからリアルタイム処理のロジックを全面的に変更
        latest_data = self.bridge.get_latest_data(self.symbol)

        if not latest_data or latest_data.get('close') is None:
            return self._load_heartbeat()
        
        # --- 取引時間外フィルター ---
        current_time = current_dt.time()
        is_morning = time(9, 0) <= current_time <= time(11, 30)
        # is_afternoon = time(12, 30) <= current_time <= time(15, 30)
        is_afternoon = time(12, 30) <= current_time <= time(23, 30)

        if not (is_morning or is_afternoon):
            logger.debug(f"[{self.symbol}] 取引時間外のためTickを無視: {current_time}")
            return None

        # --- BarBuilderにTickデータを渡す ---
        price = latest_data['close']
        volume = latest_data.get('volume', 0.0)
        completed_bar = self.builder.add_tick(current_dt, price, volume)

        if completed_bar:
            logger.info(f"[{self.symbol}] 新規5分足完成: {completed_bar['timestamp']}")
            self._populate_lines_from_dict(completed_bar)
            return True
        else:
            # バーはまだ形成中
            return None

    def _load_heartbeat(self):
        # 最後の足の終値がなければハートビートは送らない
        if len(self.lines.close) == 0 or self.lines.close[0] is None:
             return None
             
        last_close = self.lines.close[0]
        epsilon = 0.0 if last_close is None else last_close * 0.0001
        
        current_dt = datetime.now()
        row = {
            'timestamp': current_dt, 'open': last_close, 'high': last_close + epsilon,
            'low': last_close, 'close': last_close, 'volume': 0, 'openinterest': 0
        }
        
        self._populate_lines_from_dict(row, is_heartbeat=True)
        logger.debug(f"[{self.symbol}] ハートビート供給: Close={last_close}")
        return True
        
    def _populate_lines_from_dict(self, bar_dict: dict, is_heartbeat: bool = False):
        """[新規] 辞書から足データをラインに設定する"""
        dt = bar_dict['timestamp']
        self.lines.datetime[0] = self.date2num(dt)
        self.lines.open[0] = float(bar_dict['open'])
        self.lines.high[0] = float(bar_dict['high'])
        self.lines.low[0] = float(bar_dict['low'])
        self.lines.close[0] = float(bar_dict['close'])
        self.lines.volume[0] = float(bar_dict.get('volume', 0))
        self.lines.openinterest[0] = float(bar_dict.get('openinterest', 0))
        if not is_heartbeat:
            self.last_dt = dt

    def _populate_lines_from_series(self, bar_series: pd.Series):
        """[修正] 元の _populate_lines メソッドをリネーム"""
        dt = pd.to_datetime(bar_series.name).to_pydatetime()
        self.lines.datetime[0] = self.date2num(dt)
        self.lines.open[0] = float(bar_series['open'])
        self.lines.high[0] = float(bar_series['high'])
        self.lines.low[0] = float(bar_series['low'])
        self.lines.close[0] = float(bar_series['close'])
        self.lines.volume[0] = float(bar_series.get('volume', 0))
        self.lines.openinterest[0] = float(bar_series.get('openinterest', 0))
        self.last_dt = dt
        
    def flush(self):
        """[新規] 最後の未完成バーを処理する"""
        logger.info(f"[{self.symbol}] 最終バーのフラッシュ処理を実行...")
        final_bar = self.builder.flush()
        if final_bar:
            self._populate_lines_from_dict(final_bar)
            logger.info(f"[{self.symbol}] 最終バーを供給: {final_bar['timestamp']}")