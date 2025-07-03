import backtrader as bt

class SafeStochastic(bt.indicators.Stochastic):
    """
    ゼロ除算エラーを回避する安全なStochasticインジケーター。
    高値と安値が同じ場合に、エラーを出さずに中間値(50)を返します。
    """
    def next(self):
        if self.data.high[0] - self.data.low[0] == 0:
            self.lines.percK[0] = 50.0
            self.lines.percD[0] = 50.0
        else:
            super().next()

class VWAP(bt.Indicator):
    """
    出来高加重平均価格 (VWAP) インジケーター。
    日毎にリセットされます。
    """
    lines = ('vwap',)
    plotinfo = dict(subplot=False)

    def __init__(self):
        # 3本値の平均を計算
        self.tp = (self.data.high + self.data.low + self.data.close) / 3.0
        self.cumulative_tpv = 0.0
        self.cumulative_volume = 0.0

    def next(self):
        # 最初のバーはスキップ
        if len(self) == 1:
            return
        
        # 日付が変わったらリセット
        if self.data.datetime.date(0) != self.data.datetime.date(-1):
            self.cumulative_tpv = 0.0
            self.cumulative_volume = 0.0
        
        self.cumulative_tpv += self.tp[0] * self.data.volume[0]
        self.cumulative_volume += self.data.volume[0]

        if self.cumulative_volume > 0:
            self.lines.vwap[0] = self.cumulative_tpv / self.cumulative_volume
        else:
            self.lines.vwap[0] = self.tp[0]