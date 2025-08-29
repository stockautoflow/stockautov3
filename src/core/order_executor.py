import logging
import backtrader as bt
import copy

logger = logging.getLogger(__name__)

class OrderExecutor:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators

    def place_entry_order(self, strategy, trade_type, entry_reason, risk_per_share):
        if not risk_per_share or risk_per_share <= 1e-9:
            logger.warning("計算されたリスクが0のため、エントリーをスキップします。")
            return None

        entry_price = self.data_feeds['short'].close[0]
        sizing = self.strategy_params.get('sizing', {})
        
        size = min(
            (strategy.broker.getcash() * sizing.get('risk_per_trade', 0.01)) / risk_per_share,
            sizing.get('max_investment_per_trade', 10000000) / entry_price if entry_price > 0 else float('inf')
        )
        
        if size <= 0:
            logger.warning("計算された注文数量が0以下のため、エントリーをスキップします。")
            return None

        is_long = trade_type == 'long'
        
        sl_price = entry_price - risk_per_share if is_long else entry_price + risk_per_share
        
        tp_cond = self.strategy_params.get('exit_conditions', {}).get('take_profit')
        tp_price = 0.0
        if tp_cond:
            tp_key = self._get_atr_key_for_exit('take_profit')
            tp_atr_indicator = self.indicators.get(tp_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                current_tp_atr_val = tp_atr_indicator[0]
                if current_tp_atr_val and current_tp_atr_val > 1e-9:
                    tp_multiplier = tp_cond.get('params', {}).get('multiplier', 5.0)
                    tp_price = entry_price + current_tp_atr_val * tp_multiplier if is_long else entry_price - current_tp_atr_val * tp_multiplier

        logger.info(f"{'BUY' if is_long else 'SELL'} 注文実行中。数量: {size:.2f}, TP: {tp_price:.2f}, SL: {sl_price:.2f}")

        strategy.entry_reason = entry_reason
        strategy.tp_price = tp_price
        strategy.sl_price = sl_price
        
        return strategy.buy(size=size) if is_long else strategy.sell(size=size)

    def place_exit_orders(self, strategy, live_trading, exit_reason):
        if not strategy.getposition().size: return

        if live_trading:
            logger.info(f"ライブモードで決済実行: {exit_reason}")
            return strategy.close()
        else:
            logger.info(f"バックテストモードで決済実行: {exit_reason}")
            exit_conditions = self.strategy_params.get('exit_conditions', {})
            sl_cond = exit_conditions.get('stop_loss', {}); tp_cond = exit_conditions.get('take_profit', {})
            is_long, size = strategy.getposition().size > 0, abs(strategy.getposition().size)
            limit_order, stop_order = None, None

            if tp_cond and strategy.tp_price != 0:
                limit_order = strategy.sell(exectype=bt.Order.Limit, price=strategy.tp_price, size=size, transmit=False) if is_long else strategy.buy(exectype=bt.Order.Limit, price=strategy.tp_price, size=size, transmit=False)
                logger.info(f"利確(Limit)注文を作成: Price={strategy.tp_price:.2f}")

            if sl_cond and sl_cond.get('type') == 'atr_stoptrail':
                stop_order = strategy.sell(exectype=bt.Order.StopTrail, trailamount=strategy.risk_per_share, size=size, oco=limit_order) if is_long else strategy.buy(exectype=bt.Order.StopTrail, trailamount=strategy.risk_per_share, size=size, oco=limit_order)
                logger.info(f"損切(StopTrail)注文をOCOで発注: TrailAmount={strategy.risk_per_share:.2f}")

            return [o for o in [limit_order, stop_order] if o is not None]

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
            return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), 'atr', atr_params)
    
    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"