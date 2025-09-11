import backtrader as bt
from src.core.strategy.base import BaseStrategy
from .implementations.event_handler import RealTradeEventHandler
from .implementations.exit_signal_generator import RealTradeExitSignalGenerator
from .implementations.order_manager import RealTradeOrderManager
from .implementations.strategy_notifier import RealTradeStrategyNotifier

class RealTradeStrategy(BaseStrategy):
    def __init__(self):
        # [新規] リアルタイムフェーズ移行が完了したかを管理するフラグ
        self.realtime_phase_started = False
        super().__init__()

    def _setup_components(self, params, components):
        state_manager = components.get('state_manager')
        notifier = RealTradeStrategyNotifier(self)
        self.event_handler = RealTradeEventHandler(self, notifier, state_manager=state_manager)
        self.order_manager = RealTradeOrderManager(self, params.get('sizing', {}), self.event_handler)
        self.exit_signal_generator = RealTradeExitSignalGenerator(self, self.order_manager)

    def start(self):
        # [修正] start()メソッドでは単純にスーパークラスを呼び出すだけにする
        super().start()

    def on_history_supplied(self):
        # このメソッドはnext()から一度だけ呼び出される
        self.logger.log("リアルタイムフェーズに移行しました。")
        if self.position:
            self.logger.log(f"シミュレーションポジション({self.position.size})を強制クリアします。")
            self.position.size = 0
            self.position.price = 0.0
            self.position.long = 0
            self.position.short = 0
            self.logger.log(f"ポジションクリア完了。現在の内部ポジション状態: Size={self.position.size or 0}, Price={self.position.price or 0.0}")
        else:
            self.logger.log(f"シミュレーションポジションはありません。現在の内部ポジション状態: Size={self.position.size or 0}, Price={self.position.price or 0.0}")

    def next(self):
        # [修正] next()内でリアルタイムフェーズへの移行を検知・処理する
        if not self.realtime_phase_started:
            # データフィードが過去データの供給を完了したかを確認
            if hasattr(self.datas[0], 'history_supplied') and self.datas[0].history_supplied:
                # 移行処理を一度だけ実行
                self.on_history_supplied()
                self.realtime_phase_started = True
        
        # 移行が完了した後は、通常の取引ロジックを実行
        if self.realtime_phase_started:
            super().next()

    def inject_position(self, size: float, price: float):
        if self.position.size == size and self.position.price == price:
            return
        self.logger.log(f"外部からポジションを注入: Size={size}, Price={price}")
        self.position.size = size
        self.position.price = price
        self.exit_signal_generator.calculate_and_set_exit_prices(
            entry_price=price,
            is_long=(size > 0)
        )
        esg = self.exit_signal_generator
        self.logger.log(f"ポジション注入後の決済価格を再計算: TP={esg.tp_price:.2f}, SL={esg.sl_price:.2f}")

    def force_close_position(self):
        if not self.position:
            return
        self.logger.log(f"外部からの指示により内部ポジション({self.position.size})を決済します。")
        self.close()
        self.exit_signal_generator.tp_price = 0.0
        self.exit_signal_generator.sl_price = 0.0
        self.exit_signal_generator.risk_per_share = 0.0