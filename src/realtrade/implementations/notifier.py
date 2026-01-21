from src.core.strategy.strategy_notifier import BaseStrategyNotifier
from src.core.util import notifier as core_notifier

class RealTradeStrategyNotifier(BaseStrategyNotifier):
    """
    リアルタイムトレード用の通知クラス。
    """
    def send(self, subject, body, immediate=False):
        core_notifier.send_email(subject, body, immediate=immediate)