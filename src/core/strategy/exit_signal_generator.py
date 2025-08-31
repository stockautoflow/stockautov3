import backtrader as bt

class ExitSignalGenerator:
    """
    責務：保有中のポジションに対し、利確や損切りなどの決済シグナルを生成する。
    """
    def __init__(self, strategy, indicators, order_manager):
        self.strategy = strategy
        self.indicators = indicators
        self.order_manager = order_manager
        
        # 内部状態として決済価格を保持
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.risk_per_share = 0.0

    def are_indicators_ready(self):
        """ポジション復元に必要なATRインジケーターが計算済みか確認"""
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer(self.strategy.p.strategy_params)
        
        sl_cond = self.strategy.p.strategy_params.get('exit_conditions', {}).get('stop_loss', {})
        if not sl_cond: return False
        
        atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
        atr_key = si._get_indicator_key(sl_cond.get('timeframe'), 'atr', atr_params)
        
        atr_indicator = self.indicators.get(atr_key)
        return atr_indicator and len(atr_indicator) > 0

    def calculate_and_set_exit_prices(self, entry_price, is_long):
        """エントリー価格に基づき、利確・損切り価格を計算して内部に保持する"""
        from .strategy_initializer import StrategyInitializer
        si = StrategyInitializer(self.strategy.p.strategy_params)
        p = self.strategy.p.strategy_params
        
        exit_conditions = p.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss', {})
        tp_cond = exit_conditions.get('take_profit', {})

        # Stop Loss
        if sl_cond:
            atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
            atr_key = si._get_indicator_key(sl_cond.get('timeframe'), 'atr', atr_params)
            atr_val = self.indicators[atr_key][0]
            if atr_val and atr_val > 1e-9:
                self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
                self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share

        # Take Profit
        if tp_cond:
            atr_params = {k: v for k, v in tp_cond.get('params', {}).items() if k != 'multiplier'}
            atr_key = si._get_indicator_key(tp_cond.get('timeframe'), 'atr', atr_params)
            atr_val = self.indicators[atr_key][0]
            if atr_val and atr_val > 1e-9:
                self.tp_price = entry_price + atr_val * tp_cond.get('params', {}).get('multiplier', 5.0) if is_long else entry_price - atr_val * tp_cond.get('params', {}).get('multiplier', 5.0)

    def check_exit_conditions(self):
        """ライブ取引かバックテストかに応じて、適切な決済ロジックを呼び出す"""
        if self.strategy.p.live_trading:
            self._check_live_exit()
        # バックテストのネイティブ注文はOrderManagerが発注済みのため、ここでは何もしない

    def _check_live_exit(self):
        """リアルタイム取引での決済条件を監視し、シグナルが出たら注文を出す"""
        pos = self.strategy.getposition()
        is_long = pos.size > 0
        current_price = self.strategy.datas[0].close[0]
        logger = self.strategy.logger

        # 利確条件
        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            logger.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            self.order_manager.close_position()
            return

        # 損切り条件
        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                logger.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                self.order_manager.close_position()
                return

            # トレーリングストップの更新
            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                logger.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                self.sl_price = new_sl_price