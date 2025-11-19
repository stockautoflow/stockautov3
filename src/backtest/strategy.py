from src.core.strategy.base import BaseStrategy
from .implementations.event_handler import BacktestEventHandler
from .implementations.exit_signal_generator import BacktestExitSignalGenerator
from .implementations.order_manager import BacktestOrderManager
from .implementations.strategy_notifier import BacktestStrategyNotifier

class BacktestStrategy(BaseStrategy):
    # [リファクタリング - 実装 v2.0]
    # バックテストに必要な全てのimplementationsコンポーネントを組み立てる「司令塔」。
    # 'backtest_method' を OrderManager に渡す。
    
    # === ▼▼▼ v2.0 変更: _setup_components ▼▼▼ ===
    def _setup_components(self, params, components):
        # [抽象メソッド] 派生クラスがモード専用コンポーネントを初期化するために実装する
        
        sizing_params = params.get('sizing', {})
        
        # 1. (新規) バックテスト用のサイジング方式を取得
        method = sizing_params.get('backtest_method', 'risk_based')
        
        notifier = BacktestStrategyNotifier(self)
        self.event_handler = BacktestEventHandler(self, notifier)
        
        # 2. (変更) OrderManager に sizing_params, method を渡す
        self.order_manager = BacktestOrderManager(
            self, 
            sizing_params, 
            method, # <-- 新規追加
            self.event_handler
            # statistics=None (バックテストでは統計情報なし)
        )
        self.exit_signal_generator = BacktestExitSignalGenerator(self, self.order_manager)
    # === ▲▲▲ v2.0 変更 ▲▲▲ ===