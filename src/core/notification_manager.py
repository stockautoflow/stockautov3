import logging
from datetime import datetime, timedelta
from .util import notifier

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, live_trading, notifier_instance):
        self.live_trading = live_trading
        self.notifier = notifier_instance
        self.symbol_str = ""

    def handle_order_notification(self, order, data_feed):
        self.symbol_str = data_feed._name.split('_')[0]
        is_entry = order.info.get('is_entry')
        is_exit = order.info.get('is_exit')
        
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if not is_entry and not is_exit:
            return

        subject = ""
        body = ""
        is_immediate = False

        if order.status == order.Completed:
            if is_entry:
                subject = f"【リアルタイム取引】エントリー注文約定 ({self.symbol_str})"
                body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\n"
                        f"銘柄: {self.symbol_str}\n"
                        f"ステータス: {order.getstatusname()}\n"
                        f"方向: {'BUY' if order.isbuy() else 'SELL'}\n"
                        f"約定数量: {order.executed.size:.2f}\n"
                        f"約定価格: {order.executed.price:.2f}")
                is_immediate = True
            elif is_exit:
                pnl = order.executed.pnl
                exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
                subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.symbol_str})"
                body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\n"
                        f"銘柄: {self.symbol_str}\n"
                        f"ステータス: {order.getstatusname()} ({exit_reason})\n"
                        f"方向: {'決済BUY' if order.isbuy() else '決済SELL'}\n"
                        f"決済数量: {order.executed.size:.2f}\n"
                        f"決済価格: {order.executed.price:.2f}\n"
                        f"実現損益: {pnl:,.2f}")
                is_immediate = True
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.symbol_str})"
            body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\n"
                    f"銘柄: {self.symbol_str}\n"
                    f"ステータス: {order.getstatusname()}\n"
                    f"詳細: {order.info.get('reason', 'N/A')}")
            is_immediate = True

        if subject and body:
            self._send_notification(subject, body, is_immediate)

    def log_trade_event(self, trade, logger_instance):
        if trade.isopen:
            logger_instance.info(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
        elif trade.isclosed:
            logger_instance.info(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")

    def _send_notification(self, subject, body, immediate=False):
        if not self.live_trading:
            return

        bar_datetime = datetime.now()
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)

        if datetime.now() - bar_datetime > timedelta(minutes=5):
            logger.debug(f"過去データに基づく通知を抑制: {subject} (データ時刻: {bar_datetime})")
            return

        logger.debug(f"通知リクエストを発行: {subject} (Immediate: {immediate})")
        notifier.send_email(subject, body, immediate=immediate)