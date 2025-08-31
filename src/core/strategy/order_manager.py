import backtrader as bt

class OrderManager:
    """
    責務：生成されたシグナルに基づき、ロットサイズを計算して注文APIを実行する。
    """
    def __init__(self, strategy, sizing_params, event_handler):
        self.strategy = strategy
        self.sizing_params = sizing_params
        self.event_handler = event_handler

    def place_entry_order(self, trade_type, reason, indicators):
        """エントリー注文のサイズ計算から発注までを行う"""
        p = self.strategy.p.strategy_params
        exit_signal_generator = self.strategy.exit_signal_generator
        
        # 決済価格の計算（発注前に必要）
        entry_price = self.strategy.datas[0].close[0]
        is_long = trade_type == 'long'
        exit_signal_generator.calculate_and_set_exit_prices(entry_price, is_long)
        
        risk_per_share = exit_signal_generator.risk_per_share
        if risk_per_share < 1e-9:
            self.strategy.logger.log(f"計算されたリスクが0のため、エントリーをスキップ。")
            return

        # 注文サイズの計算
        cash = self.strategy.broker.getcash()
        risk_capital = cash * self.sizing_params.get('risk_per_trade', 0.01)
        max_investment = self.sizing_params.get('max_investment_per_trade', 1e7)
        
        size1 = risk_capital / risk_per_share
        size2 = max_investment / entry_price if entry_price > 0 else float('inf')
        size = min(size1, size2)

        if size <= 0: return

        # エントリー注文の発注
        if is_long:
            self.strategy.entry_order = self.strategy.buy(size=size)
        else:
            self.strategy.entry_order = self.strategy.sell(size=size)
        
        # イベントハンドラに通知
        self.event_handler.on_entry_order_placed(
            trade_type=trade_type, size=size, reason=reason,
            tp_price=exit_signal_generator.tp_price,
            sl_price=exit_signal_generator.sl_price
        )

    def place_backtest_exit_orders(self):
        """バックテスト専用のOCO決済注文（利確・損切り）を発注する"""
        if not self.strategy.position: return
        
        pos = self.strategy.position
        is_long, size = pos.size > 0, abs(pos.size)
        
        exit_signal_generator = self.strategy.exit_signal_generator
        tp_price = exit_signal_generator.tp_price
        risk_per_share = exit_signal_generator.risk_per_share
        
        limit_order, stop_order = None, None

        if tp_price != 0:
            if is_long:
                limit_order = self.strategy.sell(exectype=bt.Order.Limit, price=tp_price, size=size, transmit=False)
            else:
                limit_order = self.strategy.buy(exectype=bt.Order.Limit, price=tp_price, size=size, transmit=False)

        if risk_per_share > 0:
            if is_long:
                stop_order = self.strategy.sell(exectype=bt.Order.StopTrail, trailamount=risk_per_share, size=size, oco=limit_order)
            else:
                stop_order = self.strategy.buy(exectype=bt.Order.StopTrail, trailamount=risk_per_share, size=size, oco=limit_order)

        self.strategy.exit_orders = [o for o in [limit_order, stop_order] if o is not None]

    def close_position(self):
        """現在のポジションを決済する注文を発注する"""
        self.strategy.exit_orders.append(self.strategy.close())