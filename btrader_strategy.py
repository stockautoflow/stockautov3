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
        self.stop_order = None
        self.limit_order = None

        self.entry_reason = ""
        self.executed_size = 0
        self.initial_sl_price = 0
        self.final_sl_price = 0
        self.tp_price = 0

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
            if cond.get('type') in ['atr_multiple', 'atr_trailing_stop']:
                atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
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
        if order.status in [order.Submitted, order.Accepted]: return

        if order.status == order.Completed:
            self.log(f"{order.getstatusname()}: {'BUY' if order.isbuy() else 'SELL'} Executed, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
            if self.entry_order and self.entry_order.ref == order.ref:
                self.log(f"エントリー成功。ポジションサイズ: {self.position.size}")
                self.executed_size = order.executed.size
                self.entry_order = None
                exit_conds = self.strategy_params.get('exit_conditions', {})
                if self.position.size > 0:
                    if 'take_profit' in exit_conds and exit_conds['take_profit']:
                        self.limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=self.position.size)
                        self.log(f"利確(Limit)注文発注: Price={self.tp_price:.2f}")
                    self.stop_order = self.sell(exectype=bt.Order.Stop, price=self.initial_sl_price, size=self.position.size)
                    self.log(f"損切(Stop)注文発注: Price={self.initial_sl_price:.2f}")
                elif self.position.size < 0:
                    if 'take_profit' in exit_conds and exit_conds['take_profit']:
                        self.limit_order = self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=abs(self.position.size))
                        self.log(f"利確(Limit)注文発注: Price={self.tp_price:.2f}")
                    self.stop_order = self.buy(exectype=bt.Order.Stop, price=self.initial_sl_price, size=abs(self.position.size))
                    self.log(f"損切(Stop)注文発注: Price={self.initial_sl_price:.2f}")

            elif self.stop_order and self.stop_order.ref == order.ref:
                self.log(f"損切り注文約定。")
                if self.limit_order and self.limit_order.alive(): self.broker.cancel(self.limit_order)
                self.stop_order, self.limit_order = None, None
            elif self.limit_order and self.limit_order.ref == order.ref:
                self.log(f"利確注文約定。")
                if self.stop_order and self.stop_order.alive(): self.broker.cancel(self.stop_order)
                self.stop_order, self.limit_order = None, None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"注文失敗/キャンセル: {order.getstatusname()}")
            if self.entry_order and self.entry_order.ref == order.ref: self.entry_order = None
            elif self.stop_order and self.stop_order.ref == order.ref: self.stop_order = None
            elif self.limit_order and self.limit_order.ref == order.ref: self.limit_order = None

    def notify_trade(self, trade):
        if not trade.isclosed: return
        self.log(f"トレードクローズ, PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")
        self.entry_order = self.stop_order = self.limit_order = None
        # self.executed_size = 0 <- !注意! executed_size はここではリセットしない

    def next(self):
        if self.position:
            sl_cond = self.strategy_params.get('exit_conditions', {}).get('stop_loss', {})
            if sl_cond.get('type') == 'atr_trailing_stop' and self.stop_order and self.stop_order.alive():
                atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', {k:v for k,v in sl_cond['params'].items() if k!='multiplier'})
                atr_val = self.indicators.get(atr_key)[0]
                multiplier = sl_cond['params']['multiplier']

                new_stop_price = 0
                current_stop = self.stop_order.created.price

                if self.position.size > 0:
                    new_stop_price = self.data.close[0] - atr_val * multiplier
                    if new_stop_price > current_stop:
                        self.broker.cancel(self.stop_order)
                        self.stop_order = self.sell(exectype=bt.Order.Stop, price=new_stop_price, size=self.position.size)
                        self.final_sl_price = new_stop_price
                        self.log(f"損切り価格を更新(Long): {current_stop:.2f} -> {new_stop_price:.2f}")

                elif self.position.size < 0:
                    new_stop_price = self.data.close[0] + atr_val * multiplier
                    if new_stop_price < current_stop:
                        self.broker.cancel(self.stop_order)
                        self.stop_order = self.buy(exectype=bt.Order.Stop, price=new_stop_price, size=abs(self.position.size))
                        self.final_sl_price = new_stop_price
                        self.log(f"損切り価格を更新(Short): {current_stop:.2f} -> {new_stop_price:.2f}")
            return

        if self.entry_order: return

        exit_conds = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conds.get('stop_loss', {})
        tp_cond = exit_conds.get('take_profit', {})

        atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', {k:v for k,v in sl_cond['params'].items() if k!='multiplier'})
        atr_val = self.indicators.get(atr_key)[0]
        if not atr_val or atr_val <= 0: return

        risk_per_share = atr_val * sl_cond['params']['multiplier']
        size = (self.broker.get_cash() * self.strategy_params.get('sizing',{}).get('risk_per_trade',0.01)) / risk_per_share
        entry_price = self.data_feeds['short'].close[0]

        def place_order(trade_type, reason):
            self.executed_size = 0 # 新規注文発行時にリセット
            self.entry_reason = reason
            is_long = trade_type == 'long'

            sl_price = entry_price - risk_per_share if is_long else entry_price + risk_per_share
            self.initial_sl_price = self.final_sl_price = sl_price

            if tp_cond:
                tp_atr_key = self._get_indicator_key(tp_cond['timeframe'], 'atr', {k:v for k,v in tp_cond['params'].items() if k!='multiplier'})
                tp_atr_val = self.indicators.get(tp_atr_key)[0]
                self.tp_price = entry_price + tp_atr_val * tp_cond['params']['multiplier'] if is_long else entry_price - tp_atr_val * tp_cond['params']['multiplier']

            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, SL: {self.initial_sl_price:.2f}, TP: {self.tp_price if tp_cond else 'N/A'}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)

        if self.strategy_params.get('trading_mode', {}).get('long_enabled'):
            met, reason = self._check_all_conditions('long')
            if met: place_order('long', reason)

        if not self.entry_order and self.strategy_params.get('trading_mode', {}).get('short_enabled'):
            met, reason = self._check_all_conditions('short')
            if met: place_order('short', reason)

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