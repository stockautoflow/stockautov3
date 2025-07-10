import backtrader as bt
import collections

class SafeStochastic(bt.indicators.Stochastic):
    def next(self):
        # 高値と安値が同じ場合に発生するゼロ除算を回避
        if self.data.high[0] - self.data.low[0] == 0:
            self.lines.percK[0] = 50.0
            self.lines.percD[0] = 50.0
        else:
            super().next()

class VWAP(bt.Indicator):
    lines = ('vwap',)
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.tp = (self.data.high + self.data.low + self.data.close) / 3.0
        self.cumulative_tpv = 0.0
        self.cumulative_volume = 0.0

    def next(self):
        if len(self) == 1:
            return
        # 日付が変わったらリセット
        if self.data.datetime.date(0) != self.data.datetime.date(-1):
            self.cumulative_tpv = 0.0
            self.cumulative_volume = 0.0
        
        self.cumulative_tpv += self.tp[0] * self.data.volume[0]
        self.cumulative_volume += self.data.volume[0]
        
        # 出来高が0の場合のゼロ除算を回避
        if self.cumulative_volume > 0:
            self.lines.vwap[0] = self.cumulative_tpv / self.cumulative_volume
        else:
            self.lines.vwap[0] = self.tp[0]

class SafeADX(bt.Indicator):
    """
    【最終版】標準ADXの計算ロジックを完全に内包し、外部依存をなくした
    「完全自己完結型」のADXインジケーター。
    これにより、計算の正確性とシステムの堅牢性を完全に両立させる。
    """
    lines = ('adx', 'plusDI', 'minusDI',)
    params = (('period', 14),)
    alias = ('ADX',)

    def __init__(self):
        self.p.period_wilder = self.p.period * 2 - 1
        
        # 内部計算用の変数を初期化
        self.tr = 0.0
        self.plus_dm = 0.0
        self.minus_dm = 0.0
        self.plus_di = 0.0
        self.minus_di = 0.0
        self.adx = 0.0
        
        # DXの履歴を保持するためのdeque
        self.dx_history = collections.deque(maxlen=self.p.period)

    def _wilder_smooth(self, prev_val, current_val):
        return prev_val - (prev_val / self.p.period) + current_val

    def next(self):
        high = self.data.high[0]
        low = self.data.low[0]
        close = self.data.close[0]
        prev_high = self.data.high[-1]
        prev_low = self.data.low[-1]
        prev_close = self.data.close[-1]

        # --- True Rangeの計算 ---
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        current_tr = max(tr1, tr2, tr3)
        self.tr = self._wilder_smooth(self.tr, current_tr)

        # --- +DM, -DMの計算 ---
        move_up = high - prev_high
        move_down = prev_low - low
        
        current_plus_dm = 0.0
        if move_up > move_down and move_up > 0:
            current_plus_dm = move_up
        
        current_minus_dm = 0.0
        if move_down > move_up and move_down > 0:
            current_minus_dm = move_down
            
        self.plus_dm = self._wilder_smooth(self.plus_dm, current_plus_dm)
        self.minus_dm = self._wilder_smooth(self.minus_dm, current_minus_dm)

        # --- +DI, -DIの計算 (ゼロ除算回避) ---
        if self.tr > 1e-9:
            self.plus_di = 100.0 * self.plus_dm / self.tr
            self.minus_di = 100.0 * self.minus_dm / self.tr
        else:
            self.plus_di = 0.0
            self.minus_di = 0.0
            
        self.lines.plusDI[0] = self.plus_di
        self.lines.minusDI[0] = self.minus_di

        # --- DX, ADXの計算 (ゼロ除算回避) ---
        di_sum = self.plus_di + self.minus_di
        dx = 0.0
        if di_sum > 1e-9:
            dx = 100.0 * abs(self.plus_di - self.minus_di) / di_sum
        
        self.dx_history.append(dx)
        
        if len(self.dx_history) == self.p.period:
            if len(self) == self.p.period: # 最初のADX計算
                self.adx = sum(self.dx_history) / self.p.period
            else: # 2回目以降のADX計算
                self.adx = (self.adx * (self.p.period - 1) + dx) / self.p.period

        self.lines.adx[0] = self.adx