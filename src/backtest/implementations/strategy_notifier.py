from src.core.strategy.strategy_notifier import BaseStrategyNotifier

class BacktestStrategyNotifier(BaseStrategyNotifier):
    """
    [リファクタリング - 実装]
    バックテスト中は通知を行わない。
    """
    def send(self, subject, body, immediate=False):
        pass