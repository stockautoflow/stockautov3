import backtrader as bt, yaml, logging

class MultiTimeFrameStrategy(bt.Strategy):
    params = (('strategy_file', 'strategy.yml'),)

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        with open(self.p.strategy_file, 'r', encoding='utf-8') as f:
            self.strategy_params = yaml.safe_load(f)
        
        p = self.strategy_params
        self.short_data, self.medium_data, self.long_data = self.datas[0], self.datas[1], self.datas[2]
        self.long_ema = bt.indicators.EMA(self.long_data.close, period=p['indicators']['long_ema_period'])
        self.medium_rsi = bt.indicators.RSI(self.medium_data.close, period=p['indicators']['medium_rsi_period'])
        self.short_ema_fast = bt.indicators.EMA(self.short_data.close, period=p['indicators']['short_ema_fast'])
        self.short_ema_slow = bt.indicators.EMA(self.short_data.close, period=p['indicators']['short_ema_slow'])
        self.short_cross = bt.indicators.CrossOver(self.short_ema_fast, self.short_ema_slow)
        self.atr = bt.indicators.ATR(self.short_data, period=p['indicators']['atr_period'])
        self.order = None
        self.trade_size = 0
        self.entry_reason = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        if order.status == order.Completed:
            if order.isbuy(): self.log(f"BUY EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
            elif order.issell(): self.log(f"SELL EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]: self.log(f"Order {order.getstatusname()}")
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed: 
            self.trade_size = trade.size
            return
        self.log(f"OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}")

    def next(self):
        if self.order or self.position: return
        
        p = self.strategy_params
        long_ok = self.long_data.close[0] > self.long_ema[0]
        filters = p['filters']
        medium_ok = filters['medium_rsi_lower'] < self.medium_rsi[0] < filters['medium_rsi_upper']
        short_ok = self.short_cross[0] > 0

        if long_ok and medium_ok and short_ok:
            exit_rules = p['exit_rules']
            atr_val = self.atr[0]
            if atr_val == 0: return

            stop_loss = self.short_data.close[0] - atr_val * exit_rules['stop_loss_atr_multiplier']
            take_profit = self.short_data.close[0] + atr_val * exit_rules['take_profit_atr_multiplier']
            
            sizing_params = p['sizing']
            cash = self.broker.get_cash()
            risk_per_share = atr_val * exit_rules['stop_loss_atr_multiplier']
            allowed_risk_amount = cash * sizing_params['risk_per_trade']
            size = allowed_risk_amount / risk_per_share if risk_per_share > 0 else 0

            self.entry_reason = f"L:C>EMA({p['indicators']['long_ema_period']}), M:RSI({p['indicators']['medium_rsi_period']})={self.medium_rsi[0]:.1f}, S:Cross"
            
            self.log(f"BUY CREATE, Price: {self.short_data.close[0]:.2f}, Size: {size:.2f}, Reason: {self.entry_reason}")
            self.order = self.buy_bracket(size=size, price=self.short_data.close[0], limitprice=take_profit, stopprice=stop_loss)
    
    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        self.logger.info(f'{dt.isoformat()} - {txt}')