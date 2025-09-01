class BaseEventHandler:
    """
    [リファクタリング]
    注文イベントの共通フローを定義する基底クラス。
    約定時の具体的な処理は抽象メソッドとして定義する。
    """
    def __init__(self, strategy, notifier, **kwargs):
        self.strategy = strategy
        self.logger = strategy.logger
        self.notifier = notifier
        self.current_entry_reason = ""

    def on_order_update(self, order):
        """注文ステータスを判別し、専門メソッドを呼び出す共通ロジック"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        is_entry = self.strategy.entry_order and self.strategy.entry_order.ref == order.ref
        is_exit = any(o.ref == order.ref for o in self.strategy.exit_orders)
        if not is_entry and not is_exit: return

        if order.status == order.Completed:
            if is_entry:
                self._handle_entry_completion(order)
            elif is_exit:
                self._handle_exit_completion(order)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self._handle_order_failure(order)

        if is_entry: self.strategy.entry_order = None
        if is_exit: self.strategy.exit_orders = []

    def on_entry_order_placed(self, trade_type, size, reason, tp_price, sl_price):
        self.current_entry_reason = reason
        is_long = trade_type == 'long'
        self.logger.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, TP: {tp_price:.2f}, SL: {sl_price:.2f}")

    def _handle_entry_completion(self, order):
        """[抽象メソッド] エントリー約定時の処理"""
        raise NotImplementedError

    def _handle_exit_completion(self, order):
        """[抽象メソッド] 決済約定時の処理"""
        raise NotImplementedError

    def _handle_order_failure(self, order):
        """注文失敗時の共通処理（ログ記録）"""
        self.logger.log(f"注文失敗/キャンセル: {order.getstatusname()}")