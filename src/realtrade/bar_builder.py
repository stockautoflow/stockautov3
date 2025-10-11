from datetime import datetime, timedelta

class BarBuilder:
    """
    リアルタイムのTickデータストリームを受け取り、定義された時間枠の
    OHLCV（始値・高値・安値・終値・出来高）バーを構築することに特化したクラス。
    """
    def __init__(self, interval_minutes: int = 5):
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive.")
        self._interval = timedelta(minutes=interval_minutes)
        self._current_bar = None
        self._last_cumulative_volume = 0.0

    def add_tick(self, timestamp: datetime, price: float, cumulative_volume: float) -> dict | None:
        """
        新しいTickデータを処理し、バーが完成した場合にそのバー(dict)を返す。
        形成中の場合はNoneを返す。
        """
        if price is None or cumulative_volume is None:
            return None # 不正なデータは無視

        # このTickが属するべきバーの開始時刻を計算 (より堅牢な方法に修正)
        interval_minutes = int(self._interval.total_seconds() / 60)
        new_minute = timestamp.minute - (timestamp.minute % interval_minutes)
        bar_start_time = timestamp.replace(minute=new_minute, second=0, microsecond=0)

        completed_bar = None

        # 形成中のバーがあり、時間枠が切り替わった場合 -> バー完成
        if self._current_bar and self._current_bar['timestamp'] != bar_start_time:
            completed_bar = self._current_bar
            self._current_bar = None

        # 新しいバーを開始
        if self._current_bar is None:
            # 差分出来高を計算（セッション跨ぎやリセットを考慮）
            if self._last_cumulative_volume > 0 and cumulative_volume >= self._last_cumulative_volume:
                tick_volume = cumulative_volume - self._last_cumulative_volume
            else:
                tick_volume = cumulative_volume # 初回Tickまたは出来高リセット時

            self._current_bar = {
                'timestamp': bar_start_time,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': tick_volume
            }
        # 既存のバーを更新
        else:
            self._current_bar['high'] = max(self._current_bar['high'], price)
            self._current_bar['low'] = min(self._current_bar['low'], price)
            self._current_bar['close'] = price
            
            # 差分出来高を計算して加算
            if self._last_cumulative_volume > 0 and cumulative_volume >= self._last_cumulative_volume:
                tick_volume = cumulative_volume - self._last_cumulative_volume
                self._current_bar['volume'] += tick_volume
        
        # 最後に処理した累計出来高を更新
        self._last_cumulative_volume = cumulative_volume
        
        return completed_bar

    def flush(self) -> dict | None:
        """
        現在形成途中のバーを強制的に返し、内部状態をリセットする。
        取引終了時などに使用する。
        """
        if self._current_bar:
            final_bar = self._current_bar
            self._current_bar = None
            self._last_cumulative_volume = 0.0
            return final_bar
        return None