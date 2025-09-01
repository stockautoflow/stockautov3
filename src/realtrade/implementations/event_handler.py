import backtrader as bt
from src.core.strategy.event_handler import BaseEventHandler

class RealTradeEventHandler(BaseEventHandler):
    """
    [リファクタリング - 実装]
    リアルタイム取引用のイベントハンドラ。
    状態の永続化と外部通知の責務を持つ。
    """
    def __init__(self, strategy, notifier, state_manager=None):
        super().__init__(strategy, notifier)
        self.state_manager = state_manager

    def on_entry_order_placed(self, trade_type, size, reason, tp_price, sl_price):
        super().on_entry_order_placed(trade_type, size, reason, tp_price, sl_price)
        is_long = trade_type == 'long'
        subject = f"【RT】新規注文発注 ({self.strategy.data0._name})"
        body = (f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\n"
                f"銘柄: {self.strategy.data0._name}\n"
                f"方向: {'BUY' if is_long else 'SELL'}\n数量: {size:.2f}\n"
                f"--- エントリー根拠 ---\n{reason}")
        self.notifier.send(subject, body, immediate=True)

    def _handle_entry_completion(self, order):
        self.logger.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
        subject = f"【RT】エントリー注文約定 ({self.strategy.data0._name})"
        body = (f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\n"
                f"約定数量: {order.executed.size:.2f}\n約定価格: {order.executed.price:.2f}")
        self.notifier.send(subject, body, immediate=True)
        # 決済価格を再計算
        self.strategy.exit_signal_generator.calculate_and_set_exit_prices(
            entry_price=order.executed.price, is_long=order.isbuy()
        )
        esg = self.strategy.exit_signal_generator
        self.logger.log(f"ライブモード決済監視開始: TP={esg.tp_price:.2f}, Initial SL={esg.sl_price:.2f}")
        self._update_trade_persistence(order)

    def _handle_exit_completion(self, order):
        pnl = order.executed.pnl
        exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
        self.logger.log(f"決済完了。 PNL: {pnl:,.2f} ({exit_reason})")
        subject = f"【RT】決済完了 - {exit_reason} ({self.strategy.data0._name})"
        body = f"実現損益: {pnl:,.2f}"
        self.notifier.send(subject, body, immediate=True)
        # 決済価格リセット
        esg = self.strategy.exit_signal_generator
        esg.tp_price, esg.sl_price = 0.0, 0.0
        self._update_trade_persistence(order)

    def _handle_order_failure(self, order):
        super()._handle_order_failure(order)
        subject = f"【RT】注文失敗/キャンセル ({self.strategy.data0._name})"
        body = f"ステータス: {order.getstatusname()}"
        self.notifier.send(subject, body, immediate=True)

    def _update_trade_persistence(self, order):
        if not self.state_manager: return
        symbol = order.data._name
        position = self.strategy.broker.getposition(order.data)
        if position.size == 0:
            self.state_manager.delete_position(symbol)
            self.logger.log(f"StateManager: ポジションをDBから削除: {symbol}")
        else:
            entry_dt = bt.num2date(order.executed.dt).isoformat()
            self.state_manager.save_position(symbol, position.size, position.price, entry_dt)
            self.logger.log(f"StateManager: ポジションをDBに保存/更新: {symbol} (Size: {position.size})")