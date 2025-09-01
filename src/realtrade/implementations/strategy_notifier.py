from datetime import datetime, timedelta
import logging
from src.core.util import notifier
from src.core.strategy.strategy_notifier import BaseStrategyNotifier

class RealTradeStrategyNotifier(BaseStrategyNotifier):
    """
    [リファクタリング - 実装]
    実際に通知（メール送信など）を行う。
    """
    def __init__(self, strategy):
        super().__init__(strategy)
        self.logger = logging.getLogger(self.__class__.__name__)

    def send(self, subject, body, immediate=False):
        bar_datetime = self.strategy.data0.datetime.datetime(0)
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)
        if datetime.now() - bar_datetime > timedelta(minutes=5):
            self.logger.debug(f"過去データに基づく通知を抑制: {subject}")
            return
        self.logger.debug(f"通知リクエストを発行: {subject}")
        notifier.send_email(subject, body, immediate=immediate)