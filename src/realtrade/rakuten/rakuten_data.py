import backtrader as bt
from datetime import datetime, timedelta, time
import logging
import pandas as pd
import threading
import os

from ..bar_builder import BarBuilder

logger = logging.getLogger(__name__)

class RakutenData(bt.feeds.PandasData):
    
    params = (
        ('bridge', None),
        ('symbol', None),
        ('timeframe', bt.TimeFrame.Minutes),
        ('heartbeat', 1.0),
        ('save_file', None), # [新規] 保存先ファイルパス
    )

    def __init__(self):
        self._hist_df = self.p.dataname
        
        # Backtrader初期化用の空DataFrame
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
        
        # BarBuilderのインスタンスを生成
        self.builder = BarBuilder(interval_minutes=self.p.compression)

        # [新規] データ保存用バッファと設定
        self.save_file = self.p.save_file
        self._new_bars = [] 

        self.history_supplied = False if (self._hist_df is not None and not self._hist_df.empty) else True

    def stop(self):
        self._stopevent.set()

    def save_history(self):
        """
        蓄積された当日の確定足をCSVに保存・マージする。
        """
        if not self._new_bars:
            logger.info(f"[{self.symbol}] 保存すべき新規データはありません。")
            return

        if not self.save_file:
            logger.warning(f"[{self.symbol}] 保存先ファイルが指定されていないため、履歴保存をスキップします。")
            return

        try:
            # 1. 新規データをDataFrame化
            new_df = pd.DataFrame(self._new_bars)
            new_df.rename(columns={'timestamp': 'datetime'}, inplace=True)
            if 'openinterest' not in new_df.columns:
                new_df['openinterest'] = 0

            # タイムゾーンをJSTに統一 ('Asia/Tokyo')
            if 'datetime' in new_df.columns:
                new_df['datetime'] = pd.to_datetime(new_df['datetime'])
                if new_df['datetime'].dt.tz is None:
                    new_df['datetime'] = new_df['datetime'].dt.tz_localize('Asia/Tokyo')
                else:
                    new_df['datetime'] = new_df['datetime'].dt.tz_convert('Asia/Tokyo')

            # 2. 既存データとのマージ
            if os.path.exists(self.save_file):
                try:
                    # 既存CSV読み込み
                    old_df = pd.read_csv(self.save_file, parse_dates=['datetime'])
                    old_df.columns = [c.lower() for c in old_df.columns]
                    
                    # 既存データのタイムゾーン統一
                    if 'datetime' in old_df.columns:
                         if old_df['datetime'].dt.tz is None:
                             old_df['datetime'] = old_df['datetime'].dt.tz_localize('Asia/Tokyo')
                         else:
                             old_df['datetime'] = old_df['datetime'].dt.tz_convert('Asia/Tokyo')

                    merged_df = pd.concat([old_df, new_df])
                except Exception as e:
                    logger.error(f"[{self.symbol}] 既存CSV読み込み失敗。新規作成します: {e}")
                    merged_df = new_df
            else:
                merged_df = new_df

            # 3. 重複排除とソート
            merged_df.drop_duplicates(subset=['datetime'], keep='last', inplace=True)
            merged_df.sort_values(by='datetime', inplace=True)

            # 4. 保存
            os.makedirs(os.path.dirname(self.save_file), exist_ok=True)
            merged_df.to_csv(self.save_file, index=False)
            
            logger.info(f"[{self.symbol}] 履歴データを保存しました: {self.save_file} (+{len(self._new_bars)} records)")
            
            # バッファをクリア
            self._new_bars = []

        except Exception as e:
            logger.error(f"[{self.symbol}] 履歴データの保存中にエラーが発生しました: {e}", exc_info=True)

    def _load(self):
        # 1. 過去データの供給
        if self._hist_df is not None and not self._hist_df.empty:
            row = self._hist_df.iloc[0]
            self._hist_df = self._hist_df.iloc[1:]
            self._populate_lines_from_series(row)
            logger.debug(f"[{self.symbol}] 過去データを供給: {row.name}")
            if self._hist_df.empty:
                self.history_supplied = True
            return True

        # 2. 停止判定
        if self._stopevent.is_set():
            return False

        current_dt = datetime.now()
        
        # 3. ハートビート制御 (高頻度アクセス防止)
        if self.last_dt and (current_dt - self.last_dt) < timedelta(seconds=self.p.heartbeat):
            return None
        
        # 4. データ取得
        latest_data = self.bridge.get_latest_data(self.symbol)

        if not latest_data or latest_data.get('close') is None:
            return self._load_heartbeat()
        
        # 5. 取引時間外フィルター (09:00-11:30, 12:30-15:30)
        current_time = current_dt.time()
        is_morning = time(9, 0) <= current_time <= time(11, 30)
        is_afternoon = time(12, 30) <= current_time <= time(15, 30)

        if not (is_morning or is_afternoon):
            # logger.debug(f"[{self.symbol}] 取引時間外のためTickを無視: {current_time}")
            return None

        # 6. BarBuilder処理
        price = latest_data['close']
        volume = latest_data.get('volume', 0.0)
        completed_bar = self.builder.add_tick(current_dt, price, volume)

        if completed_bar:
            logger.info(f"[{self.symbol}] 新規5分足完成: {completed_bar['timestamp']}")
            # ▼▼▼ 保存用バッファに追加 ▼▼▼
            self._new_bars.append(completed_bar.copy())
            self._populate_lines_from_dict(completed_bar)
            return True
        else:
            return None

    def _load_heartbeat(self):
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
        return True
        
    def _populate_lines_from_dict(self, bar_dict: dict, is_heartbeat: bool = False):
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
        final_bar = self.builder.flush()
        if final_bar:
            self._new_bars.append(final_bar.copy())
            self._populate_lines_from_dict(final_bar)
            logger.info(f"[{self.symbol}] 最終バーをフラッシュ供給: {final_bar['timestamp']}")