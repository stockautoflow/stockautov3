import backtrader as bt
import logging
from collections import defaultdict
import inspect # ★ 修正: inspectモジュールをインポート

class DynamicStrategy(bt.Strategy):
    params = (('strategy_params', None),)

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.p.strategy_params:
            self.logger.error("戦略パラメータが指定されていません。")
            return

        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()
        self.order = None
        self.entry_reason = None
        self.sl_price = 0
        self.tp_price = 0

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _create_indicators(self):
        indicators = {}
        p = self.p.strategy_params
        conditions = p.get('entry_conditions', {})
        exit_conds = p.get('exit_conditions', {})
        
        # 1. Collect all unique base indicator definitions
        unique_base_indicator_defs = {}
        def collect_defs(cond_list):
            for cond in cond_list:
                if 'indicator' in cond:
                    key = self._get_indicator_key(cond['timeframe'], cond['indicator']['name'], cond['indicator'].get('params', {}))
                    unique_base_indicator_defs[key] = (cond['timeframe'], cond['indicator'])
                if 'indicator1' in cond:
                    key = self._get_indicator_key(cond['timeframe'], cond['indicator1']['name'], cond['indicator1'].get('params', {}))
                    unique_base_indicator_defs[key] = (cond['timeframe'], cond['indicator1'])
                if 'indicator2' in cond:
                    key = self._get_indicator_key(cond['timeframe'], cond['indicator2']['name'], cond['indicator2'].get('params', {}))
                    unique_base_indicator_defs[key] = (cond['timeframe'], cond['indicator2'])
        
        if p.get('trading_mode', {}).get('long_enabled'): collect_defs(conditions.get('long', []))
        if p.get('trading_mode', {}).get('short_enabled'): collect_defs(conditions.get('short', []))

        for exit_type in ['take_profit', 'stop_loss']:
            cond = exit_conds.get(exit_type, {})
            if cond.get('type') == 'atr_multiple':
                atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                key = self._get_indicator_key(cond['timeframe'], 'atr', atr_params)
                unique_base_indicator_defs[key] = (cond['timeframe'], {'name': 'atr', 'params': atr_params})

        # 2. Create base indicators from unique definitions
        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
        # ★ 修正: インジケータークラスの取得ロジックを堅牢化
        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
        for key, (timeframe, ind_def) in unique_base_indicator_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            
            indicator_class = None
            # 優先順位: 1. 大文字 (例: EMA), 2.キャピタライズ (例: Ema), 3.そのまま (例: ema)
            for lookup_name in [name.upper(), name.capitalize(), name]:
                obj = getattr(bt.indicators, lookup_name, None)
                # 取得したオブジェクトが呼び出し可能なIndicatorクラスであるかチェック
                if obj and inspect.isclass(obj) and issubclass(obj, bt.Indicator):
                    indicator_class = obj
                    break # 適切なクラスが見つかったら探索終了
            
            if indicator_class:
                self.logger.debug(f"Creating base indicator: {key} using {indicator_class.__name__}")
                indicators[key] = indicator_class(self.data_feeds[timeframe], **params)
            else:
                self.logger.error(f"Indicator class '{name}' not found or is not a callable class.")
        # ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

        # 3. Create Crossover indicators
        def create_cross_indicators(cond_list):
            for cond in cond_list:
                if cond.get('type') in ['crossover', 'crossunder']:
                    tf = cond['timeframe']
                    key1 = self._get_indicator_key(tf, cond['indicator1']['name'], cond['indicator1'].get('params', {}))
                    key2 = self._get_indicator_key(tf, cond['indicator2']['name'], cond['indicator2'].get('params', {}))
                    ind1, ind2 = indicators.get(key1), indicators.get(key2)
                    if ind1 is not None and ind2 is not None:
                        cross_key = f"cross_{key1}_vs_{key2}"
                        if cross_key not in indicators:
                           self.logger.debug(f"Creating Crossover indicator: {cross_key}")
                           indicators[cross_key] = bt.indicators.CrossOver(ind1, ind2)
                    else: self.logger.error(f"Crossover Error: Base indicators not found for {key1} or {key2}")
        
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
            tgt_val = self.data_feeds[tf].lines.getline(target['value'])[0]
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
        for cond in conditions:
            if not self._evaluate_condition(cond): return False, ""
        return True, " & ".join([_format_condition_reason(c) for c in conditions])

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        if order.status == order.Completed: self.log(f"{'BUY' if order.isbuy() else 'SELL'} EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]: self.log(f"Order Canceled/Margin/Rejected: {order.getstatusname()}")
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed: return
        self.log(f"OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}")

    def next(self):
        if self.order or self.position: return
        p = self.p.strategy_params
        exit_conds, sizing_params = p.get('exit_conditions', {}), p.get('sizing', {})

        if p.get('trading_mode', {}).get('long_enabled'):
            met, reason = self._check_all_conditions('long')
            if met:
                sl_cond, tp_cond = exit_conds['stop_loss'], exit_conds['take_profit']
                atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
                atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', atr_params)
                atr_val = self.indicators.get(atr_key, [0])[0]
                if atr_val > 0:
                    risk_per_share = atr_val * sl_cond['params']['multiplier']
                    allowed_risk_amount = self.broker.get_cash() * sizing_params['risk_per_trade']
                    size = allowed_risk_amount / risk_per_share if risk_per_share > 0 else 0
                    if size > 0:
                        entry_price = self.data_feeds['short'].close[0]
                        self.sl_price, self.tp_price = entry_price - risk_per_share, entry_price + atr_val * tp_cond['params']['multiplier']
                        self.entry_reason = reason
                        self.log(f"BUY CREATE, Price: {entry_price:.2f}, Size: {size:.2f}, SL: {self.sl_price:.2f}, TP: {self.tp_price:.2f}")
                        self.order = self.buy_bracket(size=size, price=entry_price, limitprice=self.tp_price, stopprice=self.sl_price)
                        return

        if p.get('trading_mode', {}).get('short_enabled'):
            met, reason = self._check_all_conditions('short')
            if met:
                sl_cond, tp_cond = exit_conds['stop_loss'], exit_conds['take_profit']
                atr_params = {k: v for k, v in sl_cond.get('params', {}).items() if k != 'multiplier'}
                atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', atr_params)
                atr_val = self.indicators.get(atr_key, [0])[0]
                if atr_val > 0:
                    risk_per_share = atr_val * sl_cond['params']['multiplier']
                    allowed_risk_amount = self.broker.get_cash() * sizing_params['risk_per_trade']
                    size = allowed_risk_amount / risk_per_share if risk_per_share > 0 else 0
                    if size > 0:
                        entry_price = self.data_feeds['short'].close[0]
                        self.sl_price, self.tp_price = entry_price + risk_per_share, entry_price - atr_val * tp_cond['params']['multiplier']
                        self.entry_reason = reason
                        self.log(f"SELL CREATE, Price: {entry_price:.2f}, Size: {size:.2f}, SL: {self.sl_price:.2f}, TP: {self.tp_price:.2f}")
                        self.order = self.sell_bracket(size=size, price=entry_price, limitprice=self.tp_price, stopprice=self.sl_price)

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
    tgt_val = tgt['value'] if tgt['type'] == 'data' else f"({','.join(map(str, tgt['value']))})"
    if comp == "between": comp = "in"
    return f"{tf}:{ind['name']}({p}){comp}{tgt_val}"