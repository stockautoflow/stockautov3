import logging
import backtrader as bt
from src.core.strategy.event_handler import BaseEventHandler

logger = logging.getLogger(__name__)

class RealTradeEventHandler(BaseEventHandler):
    """
    リアルタイムトレード用のイベントハンドラ。
    BaseEventHandlerを継承し、約定時の通知と状態保存の実装を提供する。
    """
    def __init__(self, strategy, notifier, state_manager=None):
        super().__init__(strategy, notifier)
        self.state_manager = state_manager

    # --- BaseEventHandler の抽象メソッドを実装 ---

    def _handle_entry_completion(self, order):
        """エントリー約定時の処理: ログ、通知、DB保存"""
        self.logger.log(f"エントリー約定: Size={order.executed.size:.2f} @ {order.executed.price:.2f}")
        
        # 通知
        subject = f"【RT】エントリー約定 ({self.strategy.data0._name})"
        body = (f"日時: {bt.num2date(order.executed.dt).isoformat()}\n"
                f"銘柄: {self.strategy.data0._name}\n"
                f"数量: {order.executed.size:.2f}\n"
                f"価格: {order.executed.price:.2f}")
        self.notifier.send(subject, body, immediate=True)

        # 決済価格の再計算 (ExitSignalGenerator連携)
        self.strategy.exit_signal_generator.calculate_and_set_exit_prices(
            entry_price=order.executed.price, 
            is_long=order.isbuy()
        )
        
        # DB保存
        self._update_trade_persistence(order)

    def _handle_exit_completion(self, order):
        """決済約定時の処理: ログ、通知、DB更新"""
        pnl = order.executed.pnl
        exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
        
        self.logger.log(f"決済完了: PNL={pnl:,.2f} ({exit_reason})")
        
        # 通知
        subject = f"【RT】決済完了 - {exit_reason} ({self.strategy.data0._name})"
        body = (f"銘柄: {self.strategy.data0._name}\n"
                f"実現損益: {pnl:,.0f}円\n"
                f"価格: {order.executed.price:.2f}")
        self.notifier.send(subject, body, immediate=True)

        # 決済価格リセット
        esg = self.strategy.exit_signal_generator
        esg.tp_price, esg.sl_price = 0.0, 0.0
        
        # DB更新
        self._update_trade_persistence(order)

    # --- その他のオーバーライド ---

    def on_entry_order_placed(self, trade_type, size, reason, entry_price, tp_price, sl_price):
        """エントリー注文発注時の処理"""
        # 親クラスのログ出力
        super().on_entry_order_placed(trade_type, size, reason, entry_price, tp_price, sl_price)
        
        # 即時通知
        is_long = trade_type == 'long'
        subject = f"【RT】新規注文発注 ({self.strategy.data0._name})"
        body = (
            f"方向: {'BUY' if is_long else 'SELL'}\n"
            f"数量: {size:.2f}\n"
            f"現在値: {entry_price:.1f}\n"
            f"TP: {tp_price:.1f}, SL: {sl_price:.1f}\n"
            f"根拠: {reason}"
        )
        self.notifier.send(subject, body, immediate=True)

    def _handle_order_failure(self, order):
        """注文失敗時の処理"""
        super()._handle_order_failure(order)
        subject = f"【RT】注文失敗/キャンセル ({self.strategy.data0._name})"
        body = f"ステータス: {order.getstatusname()}"
        self.notifier.send(subject, body, immediate=True)

    def on_data_status(self, data, status):
        """データフィードの状態変化"""
        status_names = ['DELAYED', 'LIVE', 'DISCONNECTED', 'UNKNOWN']
        s_name = status_names[status] if 0 <= status < len(status_names) else str(status)
        self.logger.log(f"Data Status Changed: {data._name} -> {s_name}")

    # --- ヘルパーメソッド ---

    def _update_trade_persistence(self, order):
        """DB上のポジション情報を更新する"""
        if not self.state_manager:
            return
            
        symbol = order.data._name
        position = self.strategy.broker.getposition(order.data)
        
        if position.size == 0:
            self.state_manager.delete_position(symbol)
            self.logger.log(f"StateManager: ポジションをDBから削除: {symbol}")
        else:
            entry_dt = bt.num2date(order.executed.dt).isoformat()
            self.state_manager.save_position(symbol, position.size, position.price, entry_dt)
            self.logger.log(f"StateManager: ポジションをDBに保存/更新: {symbol} (Size: {position.size})")