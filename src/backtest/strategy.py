from src.core.strategy.base import BaseStrategy
from .implementations.event_handler import BacktestEventHandler
from .implementations.exit_signal_generator import BacktestExitSignalGenerator
from .implementations.order_manager import BacktestOrderManager
from .implementations.strategy_notifier import BacktestStrategyNotifier

class BacktestStrategy(BaseStrategy):
    """
    [リファクタリング - 実装]
    バックテストに必要な全てのimplementationsコンポーネントを組み立てる「司令塔」。
    """
    def _setup_components(self, params, components):
        notifier = BacktestStrategyNotifier(self)
        self.event_handler = BacktestEventHandler(self, notifier)
        self.order_manager = BacktestOrderManager(self, params.get('sizing', {}), self.event_handler)
        self.exit_generator = BacktestExitSignalGenerator(self, self.order_manager)