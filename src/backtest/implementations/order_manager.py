import backtrader as bt
from src.core.strategy.order_manager import BaseOrderManager

class BacktestOrderManager(BaseOrderManager):
    """
    [リファクタリング - 実装]
    バックテスト専用のネイティブOCO注文（Limit + StopTrail）を発行する。
    """
    def place_backtest_exit_orders(self):
        if not self.strategy.position: return
        pos = self.strategy.position
        is_long, size = pos.size > 0, abs(pos.size)
        
        exit_generator = self.strategy.exit_generator
        tp_price = exit_generator.tp_price
        risk_per_share = exit_generator.risk_per_share
        
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