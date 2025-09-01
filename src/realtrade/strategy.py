from src.core.strategy.base import BaseStrategy
from .implementations.event_handler import RealTradeEventHandler
from .implementations.exit_signal_generator import RealTradeExitSignalGenerator
from .implementations.order_manager import RealTradeOrderManager
from .implementations.strategy_notifier import RealTradeStrategyNotifier

class RealTradeStrategy(BaseStrategy):
    """
    [リファクタリング - 実装]
    リアルタイム取引に必要な全てのimplementationsコンポーネントを組み立てる「司令塔」。
    """
    def _setup_components(self, params, components):
        state_manager = components.get('state_manager')
        
        notifier = RealTradeStrategyNotifier(self)
        self.event_handler = RealTradeEventHandler(self, notifier, state_manager=state_manager)
        self.order_manager = RealTradeOrderManager(self, params.get('sizing', {}), self.event_handler)
        self.exit_signal_generator = RealTradeExitSignalGenerator(self, self.order_manager)