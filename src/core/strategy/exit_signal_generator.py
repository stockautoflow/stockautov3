class BaseExitSignalGenerator:
    """
    [リファクタリング]
    決済価格の計算など、モード共通のロジックを提供する基底クラス。
    決済条件の監視方法は抽象メソッドとして定義する。
    """
    def __init__(self, strategy, order_manager):
        self.strategy = strategy
        self.indicators = strategy.indicators
        self.order_manager = order_manager
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.risk_per_share = 0.0

    def are_indicators_ready(self):
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer(self.strategy.p.strategy_params)
        sl_cond = self.strategy.p.strategy_params.get('exit_conditions', {}).get('stop_loss', {})
        if not sl_cond: return False
        atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
        atr_key = si._get_indicator_key(sl_cond.get('timeframe'), 'atr', atr_params)
        atr_indicator = self.indicators.get(atr_key)
        return atr_indicator and len(atr_indicator) > 0

    def calculate_and_set_exit_prices(self, entry_price, is_long):
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer(self.strategy.p.strategy_params)
        p = self.strategy.p.strategy_params
        exit_conditions = p.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss', {})
        tp_cond = exit_conditions.get('take_profit', {})
        if sl_cond:
            atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
            atr_key = si._get_indicator_key(sl_cond.get('timeframe'), 'atr', atr_params)
            atr_val = self.indicators[atr_key][0]
            if atr_val > 1e-9:
                self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
                self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
        if tp_cond:
            atr_params = {k: v for k, v in tp_cond.get('params', {}).items() if k != 'multiplier'}
            atr_key = si._get_indicator_key(tp_cond.get('timeframe'), 'atr', atr_params)
            atr_val = self.indicators[atr_key][0]
            if atr_val > 1e-9:
                self.tp_price = entry_price + atr_val * tp_cond.get('params', {}).get('multiplier', 5.0) if is_long else entry_price - atr_val * tp_cond.get('params', {}).get('multiplier', 5.0)

    def check_exit_conditions(self):
        """[抽象メソッド] 決済条件を監視する方法"""
        raise NotImplementedError