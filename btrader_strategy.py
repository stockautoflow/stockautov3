import backtrader as bt
import logging
import inspect

def _format_condition_reason(cond):
    tf, type = cond['timeframe'][0].upper(), cond.get('type')
    if type in ['crossover', 'crossunder']:
        i1, i2 = cond['indicator1'], cond['indicator2']
        p1 = ",".join(map(str, i1.get('params', {}).values()))
        p2 = ",".join(map(str, i2.get('params', {}).values()))
        op = "X" if type == 'crossover' else "x"
        return f"{tf}:{i1['name']}({p1}){op}{i2['name']}({p2})"
    ind = cond['indicator']
    p = ",".join(map(str, ind.get('params', {}).values()))
    comp, tgt = cond['compare'], cond['target']
    tgt_val = tgt['value'] if tgt['type'] == 'data' else f"({','.join(map(str, tgt['value']))})"
    if comp == "between": comp = "in"
    return f"{tf}:{ind['name']}({p}){comp}{tgt_val}"

class DynamicStrategy(bt.Strategy):
    params = (('strategy_params', None),)

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.p.strategy_params:
            self.logger.error("戦略パラメータが指定されていません。")
            return

        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()
        
        self.entry_order = None
        self.exit_orders = []
        
        self.entry_reason = ""
        self.exit_reason = ""
        self.executed_size = 0
        self.initial_sl_price = 0
        self.initial_tp_price = 0

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _create_indicators(self):
        indicators = {}
        p = self.p.strategy_params
        conditions = p.get('entry_conditions', {})
        exit_conds = p.get('exit_conditions', {})
        
        unique_base_indicator_defs = {}
        def collect_defs(cond_list):
            for cond in cond_list:
                if 'indicator' in cond:
                    key = self._get_indicator_key(cond['timeframe'], cond['indicator']['name'], cond['indicator'].get('params', {}))
                    unique_base_indicator_defs[key] = (cond['timeframe'], cond['indicator'])
                for ind_key in ['indicator1', 'indicator2']:
                    if ind_key in cond:
                        key = self._get_indicator_key(cond['timeframe'], cond[ind_key]['name'], cond[ind_key].get('params', {}))
                        unique_base_indicator_defs[key] = (cond['timeframe'], cond[ind_key])
        
        if p.get('trading_mode', {}).get('long_enabled'): collect_defs(conditions.get('long', []))
        if p.get('trading_mode', {}).get('short_enabled'): collect_defs(conditions.get('short', []))

        for exit_type in ['take_profit', 'stop_loss', 'trailing_stop']:
            cond = exit_conds.get(exit_type, {})
            if cond.get('type', '').startswith('atr_'):
                atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                key = self._get_indicator_key(cond['timeframe'], 'atr', atr_params)
                unique_base_indicator_defs[key] = (cond['timeframe'], {'name': 'atr', 'params': atr_params})

        for key, (timeframe, ind_def) in unique_base_indicator_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            indicator_class = getattr(bt.indicators, name, None)
            if not (indicator_class and inspect.isclass(indicator_class)):
                indicator_class = getattr(bt.indicators, name.upper(), None)
            if not (indicator_class and inspect.isclass(indicator_class)):
                indicator_class = getattr(bt.indicators, name.capitalize(), None)
            
            if indicator_class:
                self.logger.debug(f"Creating base indicator: {key} using {indicator_class.__name__}")
                indicators[key] = indicator_class(self.data_feeds[timeframe], **params)
            else:
                self.logger.error(f"Indicator class '{name}' not found.")

        def create_cross_indicators(cond_list):
            for cond in cond_list:
                if cond.get('type') in ['crossover', 'crossunder']:
                    tf = cond['timeframe']
                    key1 = self._get_indicator_key(tf, cond['indicator1']['name'], cond['indicator1'].get('params', {}))
                    key2 = self._get_indicator_key(tf, cond['indicator2']['name'], cond['indicator2'].get('params', {}))
                    if key1 in indicators and key2 in indicators:
                        cross_key = f"cross_{key1}_vs_{key2}"
                        if cross_key not in indicators:
                           self.logger.debug(f"Creating Crossover: {cross_key}")
                           indicators[cross_key] = bt.indicators.CrossOver(indicators[key1], indicators[key2])
        
        if p.get('trading_mode', {}).get('long_enabled'): create_cross_indicators(conditions.get('long', []))
        if p.get('trading_mode', {}).get('short_enabled'): create_cross_indicators(conditions.get('short', []))
            
        return indicators

    def _evaluate_condition(self, cond):
        tf = cond['timeframe']
        if cond.get('type') in ['crossover', 'crossunder']:
            key1 = self._get_indicator_key(tf, cond['indicator1']['name'], cond['indicator1'].get('params', {}))
            key2 = self._get_indicator_key(tf, cond['indicator2']['name'], cond['indicator2'].get('params', {}))
            cross_key = f"cross_{key1}_vs_{key2}"
            cross_ind = self.indicators.get(cross_key)
            if cross_ind is None: return False
            return cross_ind[0] > 0 if cond['type'] == 'crossover' else cross_ind[0] < 0

        key = self._get_indicator_key(tf, cond['indicator']['name'], cond['indicator'].get('params', {}))
        indicator = self.indicators.get(key)
        if indicator is None: return False

        target, comp, ind_val = cond['target'], cond['compare'], indicator[0]
        if target['type'] == 'data':
            target_line = getattr(self.data_feeds[tf], target['value'])
            tgt_val = target_line[0]
            if comp == '>': return ind_val > tgt_val
            if comp == '<': return ind_val < tgt_val
        elif target['type'] == 'values':
            tgt_val = target['value']
            if comp == '>': return ind_val > tgt_val[0]
            if comp == '<': return ind_val < tgt_val[0]
            if comp == 'between': return tgt_val[0] < ind_val < tgt_val[1]
        return False

    def _check_all_conditions(self, trade_type):
        conditions = self.p.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions: return False, ""
        all_met = all(self._evaluate_condition(cond) for cond in conditions)
        reason = " & ".join([_format_condition_reason(c) for c in conditions]) if all_met else ""
        return all_met, reason

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if self.entry_order and self.entry_order.ref == order.ref:
                self.log(f"{'BUY' if order.isbuy() else 'SELL'} EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
                self.executed_size = order.executed.size
                self.entry_order = None
                self._place_exit_orders(order.isbuy())
            elif any(o.ref == order.ref for o in self.exit_orders):
                exit_price = order.executed.price
                if order.exectype == bt.Order.StopTrail: self.exit_reason = f"Trailing Stop ({exit_price:.2f})"
                elif order.exectype == bt.Order.Limit: self.exit_reason = f"Take Profit ({exit_price:.2f})"
                else: self.exit_reason = f"Exit ({order.getstatusname()})"
                self.log(f"EXIT ORDER COMPLETED: {self.exit_reason}")
                self.exit_orders.clear()
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order Canceled/Margin/Rejected: {order.getstatusname()}")
            if self.entry_order and self.entry_order.ref == order.ref:
                self.entry_order = None
            self.exit_orders = [o for o in self.exit_orders if o.ref != order.ref]

    def notify_trade(self, trade):
        if not trade.isclosed: return
        self.log(f"OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}")
        self.executed_size = 0
        self.entry_reason, self.exit_reason = "", ""
        self.initial_sl_price, self.initial_tp_price = 0, 0

    def next(self):
        if self.entry_order or self.position: return
        p = self.p.strategy_params
        if p.get('trading_mode', {}).get('long_enabled'):
            if self._place_entry_order('long'): return
        if p.get('trading_mode', {}).get('short_enabled'):
            if self._place_entry_order('short'): return

    def _place_entry_order(self, trade_type):
        p = self.p.strategy_params
        is_long = trade_type == 'long'
        met, reason = self._check_all_conditions(trade_type)
        if not met: return False

        sl_cond = p['exit_conditions'].get('trailing_stop') or p['exit_conditions'].get('stop_loss')
        sizing_params = p.get('sizing', {})
        if not sl_cond or not sizing_params:
            self.log("Sizing or Stop/TrailingStop conditions not defined.")
            return False

        atr_params = {k: v for k, v in sl_cond['params'].items() if k != 'multiplier'}
        atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', atr_params)
        atr_val = self.indicators.get(atr_key, [0])[0]

        if atr_val <= 0: return False
            
        risk_per_share = atr_val * sl_cond['params']['multiplier']
        size = (self.broker.get_cash() * sizing_params['risk_per_trade']) / risk_per_share if risk_per_share > 0 else 0

        if size > 0:
            self.entry_reason = reason
            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)
            return True
        return False

    def _place_exit_orders(self, is_long):
        p, entry_price = self.p.strategy_params, self.position.price
        
        ts_cond = p['exit_conditions'].get('trailing_stop')
        if ts_cond and ts_cond['type'] == 'atr_trailing':
            atr_params = {k: v for k, v in ts_cond['params'].items() if k != 'multiplier'}
            atr_key = self._get_indicator_key(ts_cond['timeframe'], 'atr', atr_params)
            atr_val = self.indicators.get(atr_key, [0])[0]
            if atr_val > 0:
                trail_amount = atr_val * ts_cond['params']['multiplier']
                self.initial_sl_price = entry_price - trail_amount if is_long else entry_price + trail_amount
                self.log(f"SUBMITTING STOP TRAIL, Amount: {trail_amount:.2f} (Initial SL: {self.initial_sl_price:.2f})")
                ex_ord = self.sell(exectype=bt.Order.StopTrail, trailamount=trail_amount) if is_long else self.buy(exectype=bt.Order.StopTrail, trailamount=trail_amount)
                self.exit_orders.append(ex_ord)
        
        tp_cond = p['exit_conditions'].get('take_profit')
        if tp_cond and tp_cond['type'] == 'atr_multiple':
            atr_params = {k: v for k, v in tp_cond['params'].items() if k != 'multiplier'}
            atr_key = self._get_indicator_key(tp_cond['timeframe'], 'atr', atr_params)
            atr_val = self.indicators.get(atr_key, [0])[0]
            if atr_val > 0:
                tp_dist = atr_val * tp_cond['params']['multiplier']
                tp_price = entry_price + tp_dist if is_long else entry_price - tp_dist
                self.initial_tp_price = tp_price
                self.log(f"SUBMITTING LIMIT (TP), Price: {tp_price:.2f}")
                ex_ord = self.sell(exectype=bt.Order.Limit, price=tp_price) if is_long else self.buy(exectype=bt.Order.Limit, price=tp_price)
                self.exit_orders.append(ex_ord)

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        self.logger.info(f'{dt.isoformat()} - {txt}')