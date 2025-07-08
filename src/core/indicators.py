import backtrader as bt

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
    ゼロ除算の可能性を完全に排除したADXインジケーター。
    計算グラフ内でゼロ除算が発生しないよう、分母をbt.Maxで直接保護する。
    """
    lines = ('adx', 'plusDI', 'minusDI',)
    params = (('period', 14),)
    alias = ('ADX',)

    def __init__(self):
        # True RangeとATRの計算
        tr = bt.indicators.TrueRange(self.data)
        atr = bt.indicators.EMA(tr, period=self.p.period)

        # Directional Movementの計算
        h_h1 = self.data.high - self.data.high(-1)
        l1_l = self.data.low(-1) - self.data.low
        
        pdm = bt.If(h_h1 > l1_l, bt.Max(h_h1, 0), 0)
        plusDM = bt.indicators.EMA(pdm, period=self.p.period)

        mdm = bt.If(l1_l > h_h1, bt.Max(l1_l, 0), 0)
        minusDM = bt.indicators.EMA(mdm, period=self.p.period)

        # Directional Index (DI) の安全な計算
        # 分母となるatrをbt.Maxで保護
        self.lines.plusDI = 100.0 * plusDM / bt.Max(atr, 1e-9)
        self.lines.minusDI = 100.0 * minusDM / bt.Max(atr, 1e-9)

        # Average Directional Index (ADX) の安全な計算
        di_sum = self.lines.plusDI + self.lines.minusDI
        di_diff = abs(self.lines.plusDI - self.lines.minusDI)
        
        # 分母となるdi_sumをbt.Maxで保護
        dx = 100.0 * di_diff / bt.Max(di_sum, 1e-9)
        
        self.lines.adx = bt.indicators.EMA(dx, period=self.p.period)