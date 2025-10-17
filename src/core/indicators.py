import backtrader as bt
import collections

# ▼▼▼【変更箇所: SafeStochasticを完全に新しい堅牢な実装に置換】▼▼▼
class SafeStochastic(bt.Indicator):
    """
    ゼロ除算を完全に回避する堅牢なStochasticインジケーター。
    BacktraderのFull Stochasticのロジックを再現しつつ、
    計算期間内の価格レンジがゼロの場合でも安全に動作する。
    """
    lines = ('percK', 'percD',)
    params = (
        ('period', 14),
        ('period_dfast', 3),
        ('period_dslow', 3),
        ('movav', bt.ind.SMA),
    )

    def __init__(self):
        super().__init__()
        
        highest_high = bt.indicators.Highest(self.data.high, period=self.p.period)
        lowest_low = bt.indicators.Lowest(self.data.low, period=self.p.period)
        
        price_range = highest_high - lowest_low
        
        # ▼▼▼【ここからが修正箇所】▼▼▼
        # ゼロ除算を回避するため、price_rangeが0の場合は分母を1.0に設定し、
        # 分子も0にすることで結果的に0を返すようにする。
        # これにより、エラーを発生させずに計算を継続できる。
        
        # 分子 (numerator)
        num = self.data.close - lowest_low
        safe_num = bt.If(price_range > 1e-9, num, 0.0)

        # 分母 (denominator)
        den = price_range
        safe_den = bt.If(price_range > 1e-9, den, 1.0)
        
        percK_raw = 100.0 * safe_num / safe_den
        # ▲▲▲【修正箇所ここまで】▲▲▲

        self.lines.percK = self.p.movav(percK_raw, period=self.p.period_dfast)
        self.lines.percD = self.p.movav(self.lines.percK, period=self.p.period_dslow)

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
        if self.data.datetime.date(0) != self.data.datetime.date(-1):
            self.cumulative_tpv = 0.0
            self.cumulative_volume = 0.0

        self.cumulative_tpv += self.tp[0] * self.data.volume[0]
        self.cumulative_volume += self.data.volume[0]

        if self.cumulative_volume > 0:
            self.lines.vwap[0] = self.cumulative_tpv / self.cumulative_volume
        else:
            self.lines.vwap[0] = self.tp[0]

class SafeADX(bt.Indicator):
    lines = ('adx', 'plusDI', 'minusDI',)
    params = (('period', 14),)
    alias = ('ADX',)

    def __init__(self):
        self.p.period_wilder = self.p.period * 2 - 1
        self.tr = 0.0
        self.plus_dm = 0.0
        self.minus_dm = 0.0
        self.plus_di = 0.0
        self.minus_di = 0.0
        self.adx = 0.0
        self.dx_history = collections.deque(maxlen=self.p.period)

    def _wilder_smooth(self, prev_val, current_val):
        return prev_val - (prev_val / self.p.period) + current_val

    def next(self):
        high, low, close = self.data.high[0], self.data.low[0], self.data.close[0]
        prev_high, prev_low, prev_close = self.data.high[-1], self.data.low[-1], self.data.close[-1]

        current_tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        self.tr = self._wilder_smooth(self.tr, current_tr)

        move_up, move_down = high - prev_high, prev_low - low
        current_plus_dm = move_up if move_up > move_down and move_up > 0 else 0.0
        current_minus_dm = move_down if move_down > move_up and move_down > 0 else 0.0

        self.plus_dm = self._wilder_smooth(self.plus_dm, current_plus_dm)
        self.minus_dm = self._wilder_smooth(self.minus_dm, current_minus_dm)

        if self.tr > 1e-9:
            self.plus_di = 100.0 * self.plus_dm / self.tr
            self.minus_di = 100.0 * self.minus_dm / self.tr
        else:
            self.plus_di, self.minus_di = 0.0, 0.0

        self.lines.plusDI[0], self.lines.minusDI[0] = self.plus_di, self.minus_di

        di_sum = self.plus_di + self.minus_di
        dx = 100.0 * abs(self.plus_di - self.minus_di) / di_sum if di_sum > 1e-9 else 0.0
        self.dx_history.append(dx)

        if len(self) >= self.p.period:
            if len(self) == self.p.period:
                self.adx = sum(self.dx_history) / self.p.period
            else:
                self.adx = (self.adx * (self.p.period - 1) + dx) / self.p.period
        self.lines.adx[0] = self.adx

# ▼▼▼【変更箇所: SafeRSIを新規追加】▼▼▼
class SafeRSI(bt.Indicator):
    """
    ゼロ除算を完全に回避する、堅牢なRSIインジケーター。
    backtrader標準のゼロ除算回避ツール(DivByZero)を使用する。
    """
    lines = ('rsi',)
    params = (('period', 14),)

    def __init__(self):
        # 価格の変動分を計算
        delta = self.data.close - self.data.close(-1)

        # 値上がり分(gain)と値下がり分(loss)を分離
        gain = bt.If(delta > 0, delta, 0.0)
        loss = bt.If(delta < 0, -delta, 0.0)

        # EMA（指数移動平均）で平滑化
        avg_gain = bt.indicators.EMA(gain, period=self.p.period)
        avg_loss = bt.indicators.EMA(loss, period=self.p.period)

        # ▼▼▼【ここからが修正箇所】▼▼▼
        # backtrader専用のゼロ除算回避インジケーターを使用する
        # avg_lossが0の場合、結果として'inf' (無限大) を返すように設定
        rs = bt.ind.DivByZero(avg_gain, avg_loss, zero=float('inf'))
        # ▲▲▲【修正箇所ここまで】▲▲▲

        # 最終的なRSIを計算
        self.lines.rsi = 100.0 - (100.0 / (1.0 + rs))