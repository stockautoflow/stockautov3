import backtrader as bt
from .strategy_initializer import StrategyInitializer
from .position_manager import PositionManager
from .strategy_logger import StrategyLogger
from .entry_signal_generator import EntrySignalGenerator

class BaseStrategy(bt.Strategy):
    """
    [リファクタリング]
    全てのストラテジーに共通する骨格（ライフサイクル、共通コンポーネントの保持）を定義する。
    モード依存のロジックは持たず、具象クラスに処理を委譲する。
    """
    params = (
        ('strategy_params', None),
        ('strategy_components', None), # モード別のコンポーネントを受け取る
    )

    def __init__(self):
        # --- 共通コンポーネントの初期化 ---
        p = self.p.strategy_params
        components = self.p.strategy_components

        self.logger = StrategyLogger(self)
        self.initializer = StrategyInitializer(p)
        self.position_manager = PositionManager(components.get('persisted_position'))
        self.data_feeds = {
            'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]
        }
        self.indicators = self.initializer.create_indicators(self.data_feeds)
        self.entry_signal_generator = EntrySignalGenerator(self.indicators, self.data_feeds)

        # --- [リファクタリング] モード別コンポーネントのセットアップを抽象メソッドに委譲 ---
        self._setup_components(p, components)

        # --- 状態変数の初期化 ---
        self.entry_order = None
        self.exit_orders = []
        self.live_trading_started = False

    def _setup_components(self, params, components):
        """[抽象メソッド] 派生クラスがモード専用コンポーネントを初期化するために実装する"""
        raise NotImplementedError("This method must be implemented by a subclass")

    def start(self):
        self.live_trading_started = True

    def next(self):
        self.logger.log_bar_data(self.indicators)

        if not self.live_trading_started or self.datas[0].volume[0] == 0:
            return

        if self.position_manager.is_restoring:
            if self.exit_generator.are_indicators_ready():
                self.position_manager.restore_state(self, self.exit_generator)
            return

        # [リファクタリング] is_live分岐を削除
        if self.entry_order or self.exit_orders:
            return

        if self.position:
            self.exit_generator.check_exit_conditions()
        else:
            trade_type, reason = self.entry_signal_generator.check_entry_signal(self.p.strategy_params)
            if trade_type:
                self.order_manager.place_entry_order(trade_type, reason, self.indicators)

    def notify_order(self, order):
        self.event_handler.on_order_update(order)

    def notify_trade(self, trade):
        self.position_manager.on_trade_update(trade, self)