import backtrader as bt
import logging

from .strategy_initializer import StrategyInitializer
from .entry_signal_generator import EntrySignalGenerator
from .exit_signal_generator import ExitSignalGenerator
from .order_manager import OrderManager
from .position_manager import PositionManager
from .event_handler import EventHandler
from .strategy_logger import StrategyLogger
from .strategy_notifier import StrategyNotifier

class DynamicStrategy(bt.Strategy):
    """
    司令塔（オーケストレーター）として、各専門コンポーネントを統括し、
    取引のライフサイクルを管理する責務を持つ。
    """
    params = (
        ('strategy_params', None),
        ('live_trading', False),
        ('persisted_position', None),
        ('state_manager', None),
    )

    def __init__(self):
        # --- 1. ロガーと通知機能を最優先で初期化 ---
        self.logger = StrategyLogger(self)
        self.notifier = StrategyNotifier(self.p.live_trading, self)

        # --- 2. 各専門コンポーネントを初期化 ---
        self.initializer = StrategyInitializer(self.p.strategy_params)
        self.position_manager = PositionManager(self.p.persisted_position)

        # --- 3. イベントハンドラを初期化し、ロガーと通知機能、StateManagerを渡す ---
        self.event_handler = EventHandler(self, self.logger, self.notifier, self.p.state_manager)

        # --- 4. 依存関係のあるコンポーネントを初期化 ---
        self.order_manager = OrderManager(self, self.p.strategy_params.get('sizing', {}), self.event_handler)
        
        # --- 5. データフィードの辞書を作成 ---
        self.data_feeds = {
            'short': self.datas[0],
            'medium': self.datas[1],
            'long': self.datas[2]
        }
        
        # --- 6. インジケーターを生成 ---
        self.indicators = self.initializer.create_indicators(self.data_feeds)

        # --- 7. シグナル生成器を初期化 ---
        self.entry_signal_generator = EntrySignalGenerator(self.indicators, self.data_feeds)
        self.exit_signal_generator = ExitSignalGenerator(self, self.indicators, self.order_manager)
        
        # --- 8. 状態変数を初期化 ---
        self.entry_order = None
        self.exit_orders = []
        self.live_trading_started = False

    def start(self):
        """cerebro.run() 開始時に一度だけ呼び出される"""
        self.live_trading_started = True

    def next(self):
        """データフィードが更新されるたびに呼び出されるメインループ"""
        self.logger.log_bar_data(self.indicators)

        if not self.live_trading_started or self.datas[0].volume[0] == 0:
            return

        # 永続化されたポジションの復元処理
        if self.position_manager.is_restoring:
            # ATRが計算されるまで待機
            if self.exit_signal_generator.are_indicators_ready():
                self.position_manager.restore_state(self, self.exit_signal_generator)
            else:
                self.logger.log("ポジション復元待機中: インジケーターが未計算です...")
            return

        # 注文執行中の場合は何もしない
        if self.entry_order or (self.p.live_trading and self.exit_orders):
            return

        # ポジションがある場合は決済ロジックを実行
        if self.position:
            self.exit_signal_generator.check_exit_conditions()
        # ポジションがない場合はエントリーロジックを実行
        else:
            trade_type, reason = self.entry_signal_generator.check_entry_signal(self.p.strategy_params)
            if trade_type:
                self.order_manager.place_entry_order(trade_type, reason, self.indicators)

    def notify_order(self, order):
        """注文状態の更新をイベントハンドラに委譲する"""
        self.event_handler.on_order_update(order)

    def notify_trade(self, trade):
        """トレード状態の更新をポジションマネージャーに委譲する"""
        self.position_manager.on_trade_update(trade, self)