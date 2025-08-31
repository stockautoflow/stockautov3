from datetime import datetime, timedelta
import logging
# 変更: core.util から notifier 本体をインポート
from ..util import notifier

class StrategyNotifier:
    """
    責務：整形されたメッセージを受け取り、メールなどの手段で外部に通知する。
    """
    def __init__(self, live_trading, strategy):
        self.live_trading = live_trading
        self.strategy = strategy
        self.logger = logging.getLogger(self.__class__.__name__)

    def send(self, subject, body, immediate=False):
        """通知内容を外部通知システム（メール）に送信する"""
        if not self.live_trading:
            return

        # データのタイムスタンプが古すぎる場合は通知を抑制
        bar_datetime = self.strategy.data0.datetime.datetime(0)
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)

        if datetime.now() - bar_datetime > timedelta(minutes=5):
            self.logger.debug(f"過去データに基づく通知を抑制: {subject}")
            return
            
        self.logger.debug(f"通知リクエストを発行: {subject}")
        # グローバルなnotifierを呼び出す
        notifier.send_email(subject, body, immediate=immediate)