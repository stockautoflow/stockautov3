class BaseOrderManager:
    """
    [リファクタリング]
    エントリー注文のサイズ計算や発注など、モード共通のロジックを提供する基底クラス。
    バックテスト専用のOCO注文ロジックは削除された。
    """
    def __init__(self, strategy, sizing_params, event_handler):
        self.strategy = strategy
        self.sizing_params = sizing_params
        self.event_handler = event_handler

    def place_entry_order(self, trade_type, reason, indicators):
        exit_generator = self.strategy.exit_generator
        entry_price = self.strategy.datas[0].close[0]
        is_long = trade_type == 'long'
        exit_generator.calculate_and_set_exit_prices(entry_price, is_long)

        risk_per_share = exit_generator.risk_per_share
        if risk_per_share < 1e-9:
            self.strategy.logger.log("計算されたリスクが0のため、エントリーをスキップ。")
            return

        cash = self.strategy.broker.getcash()
        risk_capital = cash * self.sizing_params.get('risk_per_trade', 0.01)
        max_investment = self.sizing_params.get('max_investment_per_trade', 1e7)
        size1 = risk_capital / risk_per_share
        size2 = max_investment / entry_price if entry_price > 0 else float('inf')
        size = min(size1, size2)

        if size <= 0: return

        self.strategy.entry_order = self.strategy.buy(size=size) if is_long else self.strategy.sell(size=size)

        self.event_handler.on_entry_order_placed(
            trade_type=trade_type, size=size, reason=reason,
            tp_price=exit_generator.tp_price, sl_price=exit_generator.sl_price
        )

    def close_position(self):
        self.strategy.exit_orders.append(self.strategy.close())