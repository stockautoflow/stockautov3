import logging
from datetime import datetime
import copy

logger = logging.getLogger(__name__)

class PositionManager:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators
        
    def restore_state(self, strategy, persisted_position):
        pos_info = persisted_position
        size, price = pos_info['size'], pos_info['price']
        
        strategy.position.size = size
        strategy.position.price = price
        strategy.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])
        
        self._recalculate_exit_prices(strategy, entry_price=price, is_long=(size > 0))
        logger.info(f"ポジション復元完了。Size: {strategy.position.size}, Price: {strategy.position.price}, SL: {strategy.sl_price:.2f}, TP: {strategy.tp_price:.2f}")

    def _recalculate_exit_prices(self, strategy, entry_price, is_long):
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss')
        tp_cond = exit_conditions.get('take_profit')
        strategy.sl_price, strategy.tp_price, strategy.risk_per_share = 0.0, 0.0, 0.0

        if sl_cond:
            sl_atr_key = self._get_atr_key_for_exit('stop_loss')
            sl_atr_indicator = self.indicators.get(sl_atr_key)
            if sl_atr_indicator and len(sl_atr_indicator) > 0:
                atr_val = sl_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    strategy.risk_per_share = atr_val * sl_cond['params']['multiplier']
                    strategy.sl_price = entry_price - strategy.risk_per_share if is_long else entry_price + strategy.risk_per_share

        if tp_cond:
            tp_atr_key = self._get_atr_key_for_exit('take_profit')
            tp_atr_indicator = self.indicators.get(tp_atr_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                atr_val = tp_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    strategy.tp_price = entry_price + (atr_val * tp_cond['params']['multiplier']) if is_long else entry_price - (atr_val * tp_cond['params']['multiplier'])

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
            return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), 'atr', atr_params)

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"