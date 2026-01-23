import backtrader as bt
from src.core.strategy.base import BaseStrategy

# 実装クラスのインポート
from .implementations.order_manager import RealTradeOrderManager
from .implementations.event_handler import RealTradeEventHandler
# ▼▼▼ 修正箇所: インポート元を strategy_notifier に変更 ▼▼▼
from .implementations.strategy_notifier import RealTradeStrategyNotifier
from .implementations.exit_signal_generator import RealTradeExitSignalGenerator

class RealTradeStrategy(BaseStrategy):
    """
    リアルタイムトレード用の戦略クラス。
    """
    def __init__(self):
        self.realtime_phase_started = False
        super().__init__()

    def _setup_components(self, params, components):
        """
        リアルタイムトレード用のコンポーネントをセットアップする
        """
        state_manager = components.get('state_manager')
        statistics = components.get('statistics')
        sizing_params = params.get('sizing', {})
        
        # 設定からメソッドを取得
        method = sizing_params.get('realtrade_method', 'risk_based')
        
        # 通知・イベントハンドラの初期化
        self.notifier = RealTradeStrategyNotifier(self)
        self.event_handler = RealTradeEventHandler(self, self.notifier, state_manager=state_manager)
        
        # OrderManagerの初期化
        self.order_manager = RealTradeOrderManager(
            self, 
            sizing_params, 
            method,
            self.event_handler,
            statistics=statistics
        )
        
        # 出口戦略ジェネレータの初期化
        self.exit_signal_generator = RealTradeExitSignalGenerator(self, self.order_manager)

    def next(self):
        # 履歴データの供給完了を検知してフラグを立てる
        if not self.realtime_phase_started:
            if hasattr(self.datas[0], 'history_supplied') and self.datas[0].history_supplied:
                self.logger.log("リアルタイムフェーズに移行しました。")
                self.realtime_phase_started = True
        
        # リアルタイムフェーズの場合のみ実行
        if self.realtime_phase_started:
            super().next()

    def notify_data(self, data, status, *args, **kwargs):
        self.event_handler.on_data_status(data, status)
    
    def inject_position(self, size, price):
        if self.position.size == size and self.position.price == price:
            return
        self.logger.log(f"外部からポジションを注入: Size={size}, Price={price}")
        self.position.size = size
        self.position.price = price
        self.exit_signal_generator.calculate_and_set_exit_prices(entry_price=price, is_long=(size > 0))

    def force_close_position(self):
        if not self.position: return
        self.logger.log(f"外部からの指示により内部ポジション({self.position.size})を決済します。")
        self.close()