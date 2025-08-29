import logging

class TradeEvaluator:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_indicator_key(self, timeframe, **ind_def):
        name = ind_def.get('name')
        params = ind_def.get('params', {})
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _evaluate_single_condition(self, cond):
        tf, cond_type = cond['timeframe'], cond.get('type')
        data_feed = self.data_feeds[tf]
        if len(data_feed) == 0:
            return False, ""

        if cond_type in ['crossover', 'crossunder']:
            k1 = self._get_indicator_key(tf, **cond['indicator1'])
            k2 = self._get_indicator_key(tf, **cond['indicator2'])
            cross_key = f"cross_{k1}_vs_{k2}"
            cross_indicator = self.indicators.get(cross_key)
            
            if cross_indicator is None or len(cross_indicator) == 0: return False, ""

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or                      (cross_indicator[0] < 0 and cond_type == 'crossunder')

            p1 = ",".join(map(str, cond['indicator1'].get('params', {}).values()))
            p2 = ",".join(map(str, cond['indicator2'].get('params', {}).values()))
            reason = f"{tf[0].upper()}: {cond_type}({cond['indicator1']['name']}({p1}),{cond['indicator2']['name']}({p2}))"
            return is_met, reason

        ind = self.indicators.get(self._get_indicator_key(tf, **cond['indicator']))
        if ind is None or len(ind) == 0: return False, ""

        val, compare, target = ind[0], cond['compare'], cond['target']
        target_type, target_val = target.get('type'), None
        target_val_str = ""

        if target_type == 'data':
            target_val = getattr(data_feed, target['value'])[0]
            target_val_str = f"{target['value']} [{target_val:.2f}]"
        elif target_type == 'indicator':
            target_ind = self.indicators.get(self._get_indicator_key(tf, **target['indicator']))
            if target_ind is None or len(target_ind) == 0:
                return False, ""
            target_val = target_ind[0]
            target_val_str = f"{target['indicator']['name']}(...) [{target_val:.2f}]"
        elif target_type == 'values':
            target_val = target['value']
            target_val_str = f"[{','.join(map(str, target_val))}]" if isinstance(target_val, list) else str(target_val)

        if target_val is None: return False, ""

        is_met = False
        compare_val_for_op = target_val[0] if isinstance(target_val, list) else target_val
        
        if compare == '>': is_met = val > compare_val_for_op
        elif compare == '<': is_met = val < compare_val_for_op
        elif compare == 'between' and isinstance(target_val, list) and len(target_val) == 2:
            is_met = target_val[0] < val < target_val[1]

        params_str = ",".join(map(str, cond['indicator'].get('params', {}).values()))
        reason = f"{tf[0].upper()}: {cond['indicator']['name']}({params_str}) [{val:.2f}] {compare} {target_val_str}"
        return is_met, reason

    def _check_all_conditions(self, trade_type):
        conditions = self.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions: return False, ""

        reason_details = []
        all_conditions_met = True
        for c in conditions:
            is_met, reason_str = self._evaluate_single_condition(c)
            if not is_met:
                all_conditions_met = False
                break
            reason_details.append(reason_str)

        if all_conditions_met:
            return True, " / ".join(reason_details)
        else:
            return False, ""
            
    def evaluate_entry_conditions(self):
        trading_mode = self.strategy_params.get('trading_mode', {})
        if trading_mode.get('long_enabled', True):
            met, reason = self._check_all_conditions('long')
            if met: return 'long', reason
        if trading_mode.get('short_enabled', True):
            met, reason = self._check_all_conditions('short')
            if met: return 'short', reason
        return None, None

    def evaluate_exit_conditions(self, strategy, close_price, is_long_position):
        # ライブトレード時のリアルタイム価格に基づく決済判定のみを行う
        if strategy.tp_price != 0 and ((is_long_position and close_price >= strategy.tp_price) or (not is_long_position and close_price <= strategy.tp_price)):
            return "Take Profit"

        if strategy.sl_price != 0:
            if (is_long_position and close_price <= strategy.sl_price) or (not is_long_position and close_price >= strategy.sl_price):
                return "Stop Loss"
            
            # ATR Trailing Stopの更新ロジック
            sl_cond = strategy.strategy_params.get('exit_conditions', {}).get('stop_loss', {})
            if sl_cond.get('type') == 'atr_stoptrail':
                new_sl_price = close_price - strategy.risk_per_share if is_long_position else close_price + strategy.risk_per_share
                if (is_long_position and new_sl_price > strategy.sl_price) or (not is_long_position and new_sl_price < strategy.sl_price):
                    strategy.logger.info(f"ライブ: SL価格を更新 {strategy.sl_price:.2f} -> {new_sl_price:.2f}")
                    strategy.sl_price = new_sl_price
        
        return None