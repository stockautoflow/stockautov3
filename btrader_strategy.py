import backtrader as bt
import logging
import inspect

# === ▼▼▼ ここにカスタムインジケーターを追加 ▼▼▼ ===
class SafeStochastic(bt.indicators.Stochastic):
    # 高値と安値が同一の場合にゼロ除算エラーを発生させないStochasticインジケーター。
    # エラーを回避し、代わりに中央値である50.0を出力する。

    def next(self):
        # 分母となる(high - low)が0でないかチェック
        if self.data.high[0] - self.data.low[0] == 0:
            # ゼロの場合は計算をスキップし、固定値(50.0)を設定
            self.lines.percK[0] = 50.0
            self.lines.percD[0] = 50.0
        else:
            # ゼロでない場合は、元のStochasticの計算処理を呼び出す
            super().next()
# === ▲▲▲ ここまで ▲▲▲ ===

class DynamicStrategy(bt.Strategy):
    params = (('strategy_params', None),)

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.p.strategy_params:
            raise ValueError("戦略パラメータが指定されていません。")

        self.strategy_params = self.p.strategy_params
        # データフィードの順番を保証: 0:short, 1:medium, 2:long
        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()

        self.entry_order = None
        self.exit_orders = []

        self.entry_reason = ""
        self.entry_reason_for_trade = ""
        self.executed_size = 0
        self.risk_per_share = 0
        self.tp_price = 0
        self.current_position_entry_dt = None

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _create_indicators(self):
        indicators, unique_defs = {}, {}

        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            key = self._get_indicator_key(timeframe, **ind_def)
            if key not in unique_defs: unique_defs[key] = (timeframe, ind_def)

        for cond_list in self.strategy_params.get('entry_conditions', {}).values():
            if not isinstance(cond_list, list): continue
            for cond in cond_list:
                if not isinstance(cond, dict): continue
                tf = cond.get('timeframe');
                if not tf: continue
                add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target'].get('indicator'))

        for exit_type in ['take_profit', 'stop_loss']:
            cond = self.strategy_params.get('exit_conditions', {}).get(exit_type, {})
            if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})

        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = None
            if name.lower() == 'rsi': ind_cls = bt.indicators.RSI_Safe
            elif name.lower() == 'stochastic': ind_cls = SafeStochastic
            else:
                for n_cand in [name.upper(), name.capitalize(), name]:
                    cls_candidate = getattr(bt.indicators, n_cand, None)
                    if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                        ind_cls = cls_candidate; break
            
            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key} using class {ind_cls.__name__}")
                indicators[key] = ind_cls(self.data_feeds[timeframe], plot=False, **params)
            else: self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        for cond_list in self.strategy_params.get('entry_conditions', {}).values():
            if not isinstance(cond_list, list): continue
            for cond in cond_list:
                if not isinstance(cond, dict) or cond.get('type') not in ['crossover', 'crossunder']: continue
                k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1']); k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                if k1 in indicators and k2 in indicators:
                    cross_key = f"cross_{k1}_vs_{k2}"
                    if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2], plot=False)
        return indicators

    def _evaluate_condition(self, cond):
        tf = cond['timeframe']
        if len(self.data_feeds[tf]) == 0: return False
        if cond.get('type') in ['crossover', 'crossunder']:
            k1 = self._get_indicator_key(tf, **cond['indicator1']); k2 = self._get_indicator_key(tf, **cond['indicator2'])
            cross = self.indicators.get(f"cross_{k1}_vs_{k2}");
            if cross is None or len(cross) == 0: return False
            return cross[0] > 0 if cond['type'] == 'crossover' else cross[0] < 0

        ind = self.indicators.get(self._get_indicator_key(tf, **cond['indicator']))
        if ind is None or len(ind) == 0: return False
        
        tgt, comp, val = cond['target'], cond['compare'], ind[0]
        tgt_type = tgt.get('type')
        tgt_val = None

        if tgt_type == 'data':
            tgt_val = getattr(self.data_feeds[tf], tgt['value'])[0]
        elif tgt_type == 'indicator':
            target_ind_def = tgt['indicator']
            target_ind_key = self._get_indicator_key(tf, **target_ind_def)
            target_ind = self.indicators.get(target_ind_key)
            if target_ind is None or len(target_ind) == 0: return False
            tgt_val = target_ind[0]
        elif tgt_type == 'values':
            tgt_val = tgt['value']
        
        if tgt_val is None: self.logger.warning(f"サポートされていないターゲットタイプ: {cond}"); return False
        
        if comp == '>':
            compare_to = tgt_val[0] if isinstance(tgt_val, list) else tgt_val
            return val > compare_to
        if comp == '<':
            compare_to = tgt_val[0] if isinstance(tgt_val, list) else tgt_val
            return val < compare_to
        if comp == 'between':
            return tgt_val[0] < val < tgt_val[1]
        return False

    def _check_all_conditions(self, trade_type):
        conditions = self.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions or not all(self._evaluate_condition(c) for c in conditions): return False, ""
        return True, " & ".join([_format_condition_reason(c) for c in conditions])

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        if self.entry_order and self.entry_order.ref == order.ref and order.status == order.Completed:
            self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
            self.entry_order = None; self._place_exit_orders()
        elif any(o and o.ref == order.ref for o in self.exit_orders) and order.status == order.Completed:
            self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
            self.exit_orders = []
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"注文失敗/キャンセル: {order.getstatusname()}")
            if self.entry_order and self.entry_order.ref == order.ref: self.entry_order = None

    def notify_trade(self, trade):
        if trade.isopen:
            self.log(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
            self.current_position_entry_dt = self.data.datetime.datetime(0)
            self.executed_size = trade.size
            self.entry_reason_for_trade = self.entry_reason
        elif trade.isclosed:
            trade.executed_size = self.executed_size; trade.entry_reason_for_trade = self.entry_reason_for_trade
            self.log(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")
            self.current_position_entry_dt, self.executed_size = None, 0
            self.entry_reason, self.entry_reason_for_trade = "", ""

    def _place_exit_orders(self):
        if not self.position: return
        sl_cond, tp_cond = self.strategy_params['exit_conditions']['stop_loss'], self.strategy_params['exit_conditions'].get('take_profit')
        is_long, size = self.position.size > 0, abs(self.position.size)
        limit_order = None
        if sl_cond.get('type') == 'atr_stoptrail':
            if tp_cond:
                limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False)
                self.log(f"利確(Limit)注文を作成: Price={self.tp_price:.2f}")
            stop_order = self.sell(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order) if is_long else self.buy(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order)
            self.log(f"損切(StopTrail)注文をOCOで発注: TrailAmount={self.risk_per_share:.2f}")
            self.exit_orders = [limit_order, stop_order] if limit_order else [stop_order]
        else: # Normal SL/TP
             if tp_cond: self.exit_orders.append(self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=size) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=size))
             sl_price = self.position.price - self.risk_per_share if is_long else self.position.price + self.risk_per_share
             self.exit_orders.append(self.sell(exectype=bt.Order.Stop, price=sl_price, size=size) if is_long else self.buy(exectype=bt.Order.Stop, price=sl_price, size=size))

    def next(self):
        if self.position or self.entry_order: return
        sl_cond = self.strategy_params['exit_conditions']['stop_loss']
        atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', {k:v for k,v in sl_cond['params'].items() if k!='multiplier'})
        atr_val = self.indicators.get(atr_key)[0]
        if not atr_val or atr_val <= 0: return
        
        self.risk_per_share = atr_val * sl_cond['params']['multiplier']
        entry_price = self.data_feeds['short'].close[0]
        sizing = self.strategy_params.get('sizing', {})
        size = min((self.broker.get_cash()*sizing.get('risk_per_trade',0.01))/self.risk_per_share if self.risk_per_share>0 else float('inf'),
                   sizing.get('max_investment_per_trade', 10000000)/entry_price if entry_price>0 else float('inf'))
        if size <= 0: return

        def place_order(trade_type, reason):
            self.entry_reason, is_long = reason, trade_type == 'long'
            tp_cond = self.strategy_params['exit_conditions'].get('take_profit')
            if tp_cond:
                tp_key = self._get_indicator_key(tp_cond['timeframe'], 'atr', {k:v for k,v in tp_cond['params'].items() if k!='multiplier'})
                self.tp_price = entry_price + self.indicators.get(tp_key)[0] * tp_cond['params']['multiplier'] if is_long else entry_price - self.indicators.get(tp_key)[0] * tp_cond['params']['multiplier']
            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)

        if self.strategy_params.get('trading_mode',{}).get('long_enabled'):
            met, reason = self._check_all_conditions('long')
            if met: place_order('long', reason); return
        if not self.entry_order and self.strategy_params.get('trading_mode',{}).get('short_enabled'):
            met, reason = self._check_all_conditions('short')
            if met: place_order('short', reason)

    def log(self, txt, dt=None): self.logger.info(f'{(dt or self.datas[0].datetime.datetime(0)).isoformat()} - {txt}')

def _format_condition_reason(cond):
    tf, type = cond['timeframe'][0].upper(), cond.get('type')
    if type in ['crossover', 'crossunder']:
        i1, i2 = cond['indicator1'], cond['indicator2']
        p1, p2 = ",".join(map(str, i1.get('params', {}).values())), ",".join(map(str, i2.get('params', {}).values()))
        return f"{tf}:{i1['name']}({p1}){'X' if type=='crossover' else 'x'}{i2['name']}({p2})"
    ind, p, comp = cond['indicator'], ",".join(map(str, cond['indicator'].get('params', {}).values())), cond['compare']
    tgt, tgt_str = cond['target'], ""
    if tgt.get('type') == 'data': tgt_str = tgt.get('value', 'N/A')
    elif tgt.get('type') == 'indicator':
        tgt_def = tgt.get('indicator', {})
        tgt_str = f"{tgt_def.get('name', 'N/A')}({','.join(map(str, tgt_def.get('params', {}).values()))})"
    elif tgt.get('type') == 'values':
        value = tgt.get('value')
        tgt_str = f"({','.join(map(str, value))})" if isinstance(value, list) else str(value)
    return f"{tf}:{ind['name']}({p}){'in' if comp=='between' else comp}{tgt_str}"