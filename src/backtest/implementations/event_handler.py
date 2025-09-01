from src.core.strategy.event_handler import BaseEventHandler

class BacktestEventHandler(BaseEventHandler):
    """
    [リファクタリング - 実装]
    バックテスト専用のイベントハンドラ。
    エントリー約定後に決済用のOCO注文を発行する責務を持つ。
    """
    def _handle_entry_completion(self, order):
        self.logger.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
        # OCO決済注文の発注をオーダーマネージャーに依頼
        self.strategy.order_manager.place_backtest_exit_orders()

    def _handle_exit_completion(self, order):
        pnl = order.executed.pnl
        exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
        self.logger.log(f"決済注文完了。 PNL: {pnl:,.2f} ({exit_reason})")

    def _handle_order_failure(self, order):
        super()._handle_order_failure(order)
        # エントリー注文失敗時は決済価格をリセット
        is_entry = self.strategy.entry_order and self.strategy.entry_order.ref == order.ref
        if is_entry:
            esg = self.strategy.exit_generator
            esg.tp_price, esg.sl_price = 0.0, 0.0