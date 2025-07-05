import backtrader as bt
import logging
import inspect
import yaml
import copy
from .indicators import SafeStochastic, VWAP

class DynamicStrategy(bt.Strategy):
    params = (
        ('strategy_params', None),
        ('strategy_catalog', None),
        ('strategy_assignments', None),
        ('live_trading', False), 
    )

    def __init__(self):
        self.live_trading = self.p.live_trading
        symbol_str = self.data0._name.split('_')[0]
        
        if self.p.strategy_catalog and self.p.strategy_assignments:
            symbol = int(symbol_str) if symbol_str.isdigit() else symbol_str
            strategy_name = self.p.strategy_assignments.get(str(symbol))
            if not strategy_name:
                raise ValueError(f"銘柄 {symbol} に戦略が割り当てられていません。")
            with open('config/strategy_base.yml', 'r', encoding='utf-8') as f:
                base_strategy = yaml.safe_load(f)
            entry_strategy_def = self.p.strategy_catalog.get(strategy_name)
            if not entry_strategy_def:
                raise ValueError(f"エントリー戦略カタログに '{strategy_name}' が見つかりません。")
            self.strategy_params = copy.deepcopy(base_strategy)
            self.strategy_params.update(entry_strategy_def)
            self.logger = logging.getLogger(f"{self.__class__.__name__}-{symbol}")
        elif self.p.strategy_params:
            self.strategy_params = self.p.strategy_params
            self.logger = logging.getLogger(self.__class__.__name__)
        else:
            raise ValueError("戦略パラメータが見つかりません。")

        if not isinstance(self.strategy_params.get('exit_conditions'), dict):
            raise ValueError(f"戦略 '{self.strategy_params.get('name')}' に exit_conditions が定義されていません。")
        if not isinstance(self.strategy_params.get('exit_conditions', {}).get('stop_loss'), dict):
            raise ValueError(f"戦略 '{self.strategy_params.get('name')}' の exit_conditions に stop_loss が定義されていません。")

        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()
        self.entry_order = None
        self.exit_orders = []
        self.entry_reason = ""
        self.entry_reason_for_trade = ""
        self.executed_size = 0
        self.risk_per_share = 0.0
        self.tp_price = 0.0
        self.sl_price = 0.0
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
        
        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params.get('entry_conditions', {}).values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe');
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target'].get('indicator'))
        
        if isinstance(self.strategy_params.get('exit_conditions'), dict):
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
            elif name.lower() == 'vwap': ind_cls = VWAP
            else:
                for n_cand in [name.upper(), name.capitalize(), name]:
                    cls_candidate = getattr(bt.indicators, n_cand, None)
                    if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                        ind_cls = cls_candidate; break
            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key} using class {ind_cls.__name__}")
                indicators[key] = ind_cls(self.data_feeds[timeframe], plot=False, **params)
            else: self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        if isinstance(self.strategy_params.get('entry_conditions'), dict):
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
        if comp == '>': return val > (tgt_val[0] if isinstance(tgt_val, list) else tgt_val)
        if comp == '<': return val < (tgt_val[0] if isinstance(tgt_val, list) else tgt_val)
        if comp == 'between': return tgt_val[0] < val < tgt_val[1]
        return False

    def _check_all_conditions(self, trade_type):
        conditions = self.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions: return False, ""
        if not all(self._evaluate_condition(c) for c in conditions): return False, ""
        return True, " & ".join([_format_condition_reason(c) for c in conditions])

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        if self.entry_order and self.entry_order.ref == order.ref:
            if order.status == order.Completed:
                self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
                if not self.live_trading: self._place_native_exit_orders()
                else:
                    is_long = order.isbuy()
                    entry_price = order.executed.price
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
                    self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, Initial SL={self.sl_price:.2f}")
            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log(f"エントリー注文失敗/キャンセル: {order.getstatusname()}")
                self.sl_price, self.tp_price = 0.0, 0.0
            self.entry_order = None
        elif self.exit_orders and self.exit_orders[0].ref == order.ref:
            if order.status == order.Completed:
                self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
                self.sl_price, self.tp_price = 0.0, 0.0
                self.exit_orders = []
            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log(f"決済注文失敗/キャンセル: {order.getstatusname()}")
                self.exit_orders = []
    
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

    def _place_native_exit_orders(self):
        if not self.getposition().size: return
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss', {})
        tp_cond = exit_conditions.get('take_profit', {})
        is_long, size = self.getposition().size > 0, abs(self.getposition().size)
        limit_order = None
        if tp_cond and self.tp_price != 0:
            limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False)
            self.log(f"利確(Limit)注文を作成: Price={self.tp_price:.2f}")
        if sl_cond and sl_cond.get('type') == 'atr_stoptrail':
            stop_order = self.sell(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order) if is_long else self.buy(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order)
            self.log(f"損切(StopTrail)注文をOCOで発注: TrailAmount={self.risk_per_share:.2f}")
            self.exit_orders = [limit_order, stop_order] if limit_order else [stop_order]

    def _check_live_exit_conditions(self):
        pos = self.getposition()
        is_long = pos.size > 0
        current_price = self.data.close[0]
        if self.tp_price != 0:
            if (is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price):
                self.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
                exit_order = self.close(); self.exit_orders.append(exit_order); return
        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                self.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                exit_order = self.close(); self.exit_orders.append(exit_order); return
            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                self.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                self.sl_price = new_sl_price

    def _check_entry_conditions(self):
        exit_conditions = self.strategy_params['exit_conditions']
        sl_cond = exit_conditions['stop_loss']
        atr_key = self._get_indicator_key(sl_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in sl_cond.get('params', {}).items() if k!='multiplier'})
        if not self.indicators.get(atr_key):
             self.log(f"ATRインジケーター '{atr_key}' が見つかりません。"); return
        atr_val = self.indicators.get(atr_key)[0]
        if not atr_val or atr_val <= 0: return
        self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
        entry_price = self.data_feeds['short'].close[0]
        sizing = self.strategy_params.get('sizing', {})
        size = min((self.broker.getcash()*sizing.get('risk_per_trade',0.01))/self.risk_per_share if self.risk_per_share>0 else float('inf'),
                   sizing.get('max_investment_per_trade', 10000000)/entry_price if entry_price>0 else float('inf'))
        if size <= 0: return
        def place_order(trade_type, reason):
            self.entry_reason, is_long = reason, trade_type == 'long'
            tp_cond = exit_conditions.get('take_profit')
            if tp_cond:
                tp_key = self._get_indicator_key(tp_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in tp_cond.get('params', {}).items() if k!='multiplier'})
                if not self.indicators.get(tp_key):
                    self.log(f"ATRインジケーター '{tp_key}' が見つかりません。"); self.tp_price = 0 
                else:
                    tp_atr_val = self.indicators.get(tp_key)[0]
                    tp_multiplier = tp_cond.get('params', {}).get('multiplier', 5.0)
                    self.tp_price = entry_price + tp_atr_val * tp_multiplier if is_long else entry_price - tp_atr_val * tp_multiplier
            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, TP: {self.tp_price:.2f}, Risk/Share: {self.risk_per_share:.2f}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)
        trading_mode = self.strategy_params.get('trading_mode', {})
        if trading_mode.get('long_enabled', True):
            met, reason = self._check_all_conditions('long')
            if met: place_order('long', reason); return
        if not self.entry_order and trading_mode.get('short_enabled', True):
            met, reason = self._check_all_conditions('short')
            if met: place_order('short', reason)

    def next(self):
        if self.entry_order: return
        if self.live_trading and self.exit_orders: return
        if self.getposition().size:
            if self.live_trading: self._check_live_exit_conditions()
            return
        self._check_entry_conditions()

    def log(self, txt, dt=None):
        log_time = dt or self.data.datetime.datetime(0)
        self.logger.info(f'{log_time.isoformat()} - {txt}')

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