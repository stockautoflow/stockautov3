import backtrader as bt
import yaml
import logging

class MultiTimeFrameStrategy(bt.Strategy):
    params = (
        ('strategy_file', 'strategy.yml'),
    )

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        with open(self.p.strategy_file, 'r', encoding='utf-8') as f:
            self.strategy_params = yaml.safe_load(f)

        p = self.strategy_params
        self.short_data = self.datas[0]
        self.medium_data = self.datas[1]
        self.long_data = self.datas[2]

        self.long_ema = bt.indicators.EMA(self.long_data.close, period=p['indicators']['long_ema_period'])
        self.medium_rsi = bt.indicators.RSI(self.medium_data.close, period=p['indicators']['medium_rsi_period'])
        self.short_ema_fast = bt.indicators.EMA(self.short_data.close, period=p['indicators']['short_ema_fast'])
        self.short_ema_slow = bt.indicators.EMA(self.short_data.close, period=p['indicators']['short_ema_slow'])
        self.short_cross = bt.indicators.CrossOver(self.short_ema_fast, self.short_ema_slow)
        self.atr = bt.indicators.ATR(self.short_data, period=p['indicators']['atr_period'])
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}")
            elif order.issell():
                self.log(f"SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed: return
        self.log(f"OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}")

    def next(self):
        if self.order: return
        if not self.position:
            long_ok = self.long_data.close[0] > self.long_ema[0]
            p_filters = self.strategy_params['filters']
            medium_ok = p_filters['medium_rsi_lower'] < self.medium_rsi[0] < p_filters['medium_rsi_upper']
            short_ok = self.short_cross[0] > 0
            if long_ok and medium_ok and short_ok:
                p_exit = self.strategy_params['exit_rules']
                atr_val = self.atr[0]
                stop_loss_price = self.short_data.close[0] - atr_val * p_exit['stop_loss_atr_multiplier']
                take_profit_price = self.short_data.close[0] + atr_val * p_exit['take_profit_atr_multiplier']
                p_sizing = self.strategy_params['sizing']
                cash = self.broker.get_cash()
                size = (cash * p_sizing['order_percentage']) / self.short_data.close[0]
                self.log(f"BUY CREATE, Price: {self.short_data.close[0]:.2f}, Size: {size:.2f}")
                self.order = self.buy_bracket(size=size, price=self.short_data.close[0], limitprice=take_profit_price, stopprice=stop_loss_price)
    
    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        self.logger.info(f'{dt.isoformat()} - {txt}')

