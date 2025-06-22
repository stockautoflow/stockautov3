import backtrader as bt
import logging
import inspect

class DynamicStrategy(bt.Strategy):
    params = (('strategy_params', None),)

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.p.strategy_params:
            raise ValueError("戦略パラメータが指定されていません。")

        self.strategy_params = self.p.strategy_params
        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()

        self.entry_order = None
        self.exit_orders = []

        self.entry_reason = ""
        self.entry_reason_for_trade = "" # --- ADD: To store reason for a specific trade
        self.executed_size = 0
        self.risk_per_share = 0
        self.tp_price = 0
        self.current_position_entry_dt = None

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _create_indicators(self):
        indicators = {}
        conditions = self.strategy_params.get('entry_conditions', {})
        exit_conds = self.strategy_params.get('exit_conditions', {})
        unique_defs = {}

        def collect_defs(cond_list):
            for cond in cond_list:
                if 'indicator' in cond: unique_defs[self._get_indicator_key(cond['timeframe'], **cond['indicator'])] = (cond['timeframe'], cond['indicator'])
                if 'indicator1' in cond: unique_defs[self._get_indicator_key(cond['timeframe'], **cond['indicator1'])] = (cond['timeframe'], cond['indicator1'])
                if 'indicator2' in cond: unique_defs[self._get_indicator_key(cond['timeframe'], **cond['indicator2'])] = (cond['timeframe'], cond['indicator2'])

        if self.strategy_params.get('trading_mode', {}).get('long_enabled'): collect_defs(conditions.get('long', []))
        if self.strategy_params.get('trading_mode', {}).get('short_enabled'): collect_defs(conditions.get('short', []))

        for exit_type in ['take_profit', 'stop_loss']:
            cond = exit_conds.get(exit_type, {})
            if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                atr_params = {k: v for k, v in cond['params'].items() if k != 'multiplier'}
                key = self._get_indicator_key(cond['timeframe'], 'atr', atr_params)
                unique_defs[key] = (cond['timeframe'], {'name': 'atr', 'params': atr_params})

        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = getattr(bt.indicators, name.capitalize(), getattr(bt.indicators, name.upper(), None))
            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key}")
                indicators[key] = ind_cls(self.data_feeds[timeframe], **params)
            else: self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        def create_cross(cond_list):
            for cond in cond_list:
                if cond.get('type') in ['crossover', 'crossunder']:
                    k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1'])
                    k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    if indicators.get(k1) is not None and indicators.get(k2) is not None:
                        cross_key = f"cross_{k1}_vs_{k2}"
                        if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2])

        if self.strategy_params.get('trading_mode', {}).get('long_enabled'): create_cross(conditions.get('long', []))
        if self.strategy_params.get('trading_mode', {}).get('short_enabled'): create_cross(conditions.get('short', []))
        return indicators

    def _evaluate_condition(self, cond):
        tf = cond['timeframe']
        if cond.get('type') in ['crossover', 'crossunder']:
            k1 = self._get_indicator_key(tf, **cond['indicator1'])
            k2 = self._get_indicator_key(tf, **cond['indicator2'])
            cross = self.indicators.get(f"cross_{k1}_vs_{k2}")
            if cross is None: return False
            return cross[0] > 0 if cond['type'] == 'crossover' else cross[0] < 0

        ind = self.indicators.get(self._get_indicator_key(tf, **cond['indicator']))
        if ind is None: return False

        tgt, comp, val = cond['target'], cond['compare'], ind[0]
        if tgt['type'] == 'data': tgt_val = getattr(self.data_feeds[tf], tgt['value'])[0]
        else: tgt_val = tgt['value']

        if comp == '>': return val > tgt_val
        if comp == '<': return val < tgt_val
        if comp == 'between': return tgt_val[0] < val < tgt_val[1]
        return False

    def _check_all_conditions(self, trade_type):
        conditions = self.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not all(self._evaluate_condition(c) for c in conditions): return False, ""
        return True, " & ".join([_format_condition_reason(c) for c in conditions])

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        # エントリー注文が約定した場合
        if self.entry_order and self.entry_order.ref == order.ref and order.status == order.Completed:
            self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
            self.entry_order = None # 追跡を解除
            self._place_exit_orders() # 決済注文を発注
            return

        # 決済注文が約定した場合
        is_exit_order = any(o and o.ref == order.ref for o in self.exit_orders)
        if is_exit_order and order.status == order.Completed:
            self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
            self.exit_orders = [] # 決済注文リストをクリア
            return
            
        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"注文失敗/キャンセル: {order.getstatusname()}")
            if self.entry_order and self.entry_order.ref == order.ref:
                self.entry_order = None # エントリー失敗時はリセット

    def notify_trade(self, trade):
        if trade.isopen:
            self.log(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
            self.current_position_entry_dt = self.data.datetime.datetime(0)
            self.executed_size = trade.size
            self.entry_reason_for_trade = self.entry_reason # --- FIX: Latch the reason for the open trade
        elif trade.isclosed:
            # --- FIX: Add attributes to the trade object for the analyzer
            trade.executed_size = self.executed_size
            trade.entry_reason_for_trade = self.entry_reason_for_trade
            
            self.log(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")
            self.current_position_entry_dt = None
            self.executed_size = 0
            self.entry_reason = ""
            self.entry_reason_for_trade = "" # Reset
    
    def _place_exit_orders(self):
        if not self.position: return
        
        sl_cond = self.strategy_params['exit_conditions']['stop_loss']
        tp_cond = self.strategy_params['exit_conditions'].get('take_profit')

        is_long = self.position.size > 0
        exit_size = self.position.size if is_long else abs(self.position.size)
        
        limit_order = None
        
        if sl_cond.get('type') == 'atr_stoptrail':
            trail_amount = self.risk_per_share
            
            # 1. 利確注文を作成（送信しない）
            if tp_cond:
                limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=exit_size, transmit=False) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=exit_size, transmit=False)
                self.log(f"利確(Limit)注文を作成: Price={self.tp_price:.2f}")
            
            # 2. StopTrail注文を、上記利確注文とOCOで連携させて発注
            stop_trail_order = self.sell(exectype=bt.Order.StopTrail, trailamount=trail_amount, size=exit_size, oco=limit_order) if is_long else self.buy(exectype=bt.Order.StopTrail, trailamount=trail_amount, size=exit_size, oco=limit_order)
            self.log(f"損切(StopTrail)注文をOCOで発注: TrailAmount={trail_amount:.2f}")
            self.exit_orders = [limit_order, stop_trail_order] if limit_order else [stop_trail_order]
        else: # 手動トレーリングまたは固定損切りの場合 (v73.0のロジックを流用)
            if tp_cond:
                self.limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=exit_size) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=exit_size)
            sl_price = self.position.price - self.risk_per_share if is_long else self.position.price + self.risk_per_share
            self.stop_order = self.sell(exectype=bt.Order.Stop, price=sl_price, size=exit_size) if is_long else self.buy(exectype=bt.Order.Stop, price=sl_price, size=exit_size)
            self.exit_orders = [self.limit_order, self.stop_order]


    def next(self):
        # 幽霊トレード防止のため、手動トレーリングは完全に削除
        if self.position or self.entry_order:
            return

        sl_cond = self.strategy_params['exit_conditions']['stop_loss']
        tp_cond = self.strategy_params['exit_conditions'].get('take_profit')

        atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', {k:v for k,v in sl_cond['params'].items() if k!='multiplier'})
        atr_val = self.indicators.get(atr_key)[0]
        if not atr_val or atr_val <= 0: return

        self.risk_per_share = atr_val * sl_cond['params']['multiplier']
        entry_price = self.data_feeds['short'].close[0]
        
        sizing_params = self.strategy_params.get('sizing', {})
        risk_per_trade = sizing_params.get('risk_per_trade', 0.01)
        max_investment_per_trade = sizing_params.get('max_investment_per_trade')
        
        risk_based_size = (self.broker.get_cash() * risk_per_trade) / self.risk_per_share if self.risk_per_share > 0 else float('inf')
        amount_based_size = max_investment_per_trade / entry_price if entry_price > 0 else float('inf')
        
        size = min(risk_based_size, amount_based_size)
        if size <= 0: return

        def place_order(trade_type, reason):
            self.entry_reason = reason
            is_long = trade_type == 'long'
            
            if tp_cond:
                tp_atr_key = self._get_indicator_key(tp_cond['timeframe'], 'atr', {k:v for k,v in tp_cond['params'].items() if k!='multiplier'})
                tp_atr_val = self.indicators.get(tp_atr_key)[0]
                self.tp_price = entry_price + tp_atr_val * tp_cond['params']['multiplier'] if is_long else entry_price - tp_atr_val * tp_cond['params']['multiplier']

            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)

        if self.strategy_params.get('trading_mode', {}).get('long_enabled'):
            met, reason = self._check_all_conditions('long')
            if met:
                place_order('long', reason)
                return

        if not self.entry_order and self.strategy_params.get('trading_mode', {}).get('short_enabled'):
            met, reason = self._check_all_conditions('short')
            if met:
                place_order('short', reason)

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        self.logger.info(f'{dt.isoformat()} - {txt}')

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
    tgt_val_str = tgt['value'] if tgt['type'] == 'data' else f"({','.join(map(str, tgt['value'])) if isinstance(tgt['value'], list) else tgt['value']})"
    op_str = "in" if comp == "between" else comp
    return f"{tf}:{ind['name']}({p}){op_str}{tgt_val_str}"