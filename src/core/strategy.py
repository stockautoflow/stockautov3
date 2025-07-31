import backtrader as bt
import logging
import inspect
import yaml
import copy
import threading
from datetime import datetime
from .indicators import SafeStochastic, VWAP, SafeADX
from .util import notifier

class DynamicStrategy(bt.Strategy):
    params = (
        ('strategy_params', None),
        ('strategy_catalog', None),
        ('strategy_assignments', None),
        ('live_trading', False),
        ('persisted_position', None),
    )

    def __init__(self):
        self.live_trading = self.p.live_trading
        symbol_str = self.data0._name.split('_')[0]

        if self.p.strategy_catalog and self.p.strategy_assignments:
            symbol = int(symbol_str) if symbol_str.isdigit() else symbol_str
            strategy_name = self.p.strategy_assignments.get(str(symbol))
            if not strategy_name: raise ValueError(f"銘柄 {symbol} に戦略が割り当てられていません。")
            with open('config/strategy_base.yml', 'r', encoding='utf-8') as f:
                base_strategy = yaml.safe_load(f)
            entry_strategy_def = self.p.strategy_catalog.get(strategy_name)
            if not entry_strategy_def: raise ValueError(f"エントリー戦略カタログに '{strategy_name}' が見つかりません。")
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
        self.live_trading_started = False

        self.is_restoring = self.p.persisted_position is not None

    def start(self):
        self.live_trading_started = True

    def _send_notification(self, subject, body):
        self.logger.debug(f"メール通知をキューに追加: {subject}")
        notifier.send_email(subject, body)

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
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe')
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target']['indicator'])

        if isinstance(self.strategy_params.get('exit_conditions'), dict):
            for exit_type in ['take_profit', 'stop_loss']:
                cond = self.strategy_params['exit_conditions'].get(exit_type, {})
                if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                    atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                    add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})

        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = None

            if name.lower() == 'stochastic':
                ind_cls = SafeStochastic
            elif name.lower() == 'vwap':
                ind_cls = VWAP
            elif name.lower() == 'adx':
                ind_cls = SafeADX

            if ind_cls is None:
                cls_candidate = getattr(bt.indicators, name, None)
                if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                    ind_cls = cls_candidate

                if ind_cls is None:
                    if name.lower() == 'rsi':
                        ind_cls = bt.indicators.RSI_Safe
                    else:
                        for n_cand in [name.upper(), name.capitalize()]:
                            cls_candidate = getattr(bt.indicators, n_cand, None)
                            if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                                ind_cls = cls_candidate
                                break
            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key} using class {ind_cls.__name__}")
                indicators[key] = ind_cls(self.data_feeds[timeframe], plot=False, **params)
            else:
                self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict) or cond.get('type') not in ['crossover', 'crossunder']: continue
                    k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1']); k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    if k1 in indicators and k2 in indicators:
                        cross_key = f"cross_{k1}_vs_{k2}"
                        if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2], plot=False)
        return indicators

    def _evaluate_condition(self, cond):
        tf, cond_type = cond['timeframe'], cond.get('type')
        data_feed = self.data_feeds[tf]
        if len(data_feed) == 0:
            return False, ""

        if cond_type in ['crossover', 'crossunder']:
            k1 = self._get_indicator_key(tf, **cond['indicator1'])
            k2 = self._get_indicator_key(tf, **cond['indicator2'])
            cross_indicator = self.indicators.get(f"cross_{k1}_vs_{k2}")
            if cross_indicator is None or len(cross_indicator) == 0: return False, ""

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or                      (cross_indicator[0] < 0 and cond_type == 'crossunder')

            p1 = ",".join(map(str, cond['indicator1'].get('params', {}).values()))
            p2 = ",".join(map(str, cond['indicator2'].get('params', {}).values()))
            reason = f"{tf[0].upper()}: {cond_type}({cond['indicator1']['name']}({p1}),{cond['indicator2']['name']}({p2})) [{is_met}]"
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
            if compare == 'between':
                target_val_str = f"[{target_val[0]},{target_val[1]}]"
            else:
                target_val_str = f"[{target_val}]"

        if target_val is None: return False, ""

        is_met = False
        if compare == '>':
            compare_val = target_val[0] if isinstance(target_val, list) else target_val
            is_met = val > compare_val
        elif compare == '<':
            compare_val = target_val[0] if isinstance(target_val, list) else target_val
            is_met = val < compare_val
        elif compare == 'between':
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
            is_met, reason_str = self._evaluate_condition(c)
            if not is_met:
                all_conditions_met = False
                break
            reason_details.append(reason_str)

        if all_conditions_met:
            return True, "\n".join(reason_details)
        else:
            return False, ""

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        is_entry = self.entry_order and self.entry_order.ref == order.ref
        is_exit = any(o.ref == order.ref for o in self.exit_orders)

        if not is_entry and not is_exit:
            return

        if order.status == order.Completed:
            if is_entry:
                subject = f"【リアルタイム取引】エントリー注文約定 ({self.data0._name})"
                body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\n"
                        f"銘柄: {self.data0._name}\n"
                        f"ステータス: {order.getstatusname()}\n"
                        f"方向: {'BUY' if order.isbuy() else 'SELL'}\n"
                        f"約定数量: {order.executed.size:.2f}\n"
                        f"約定価格: {order.executed.price:.2f}")
                self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
                if not self.live_trading: self._place_native_exit_orders()
                else:
                    is_long = order.isbuy(); entry_price = order.executed.price
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
                    self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, Initial SL={self.sl_price:.2f}")

            elif is_exit:
                pnl = order.executed.pnl
                exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
                subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.data0._name})"
                body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\n"
                        f"銘柄: {self.data0._name}\n"
                        f"ステータス: {order.getstatusname()} ({exit_reason})\n"
                        f"方向: {'決済BUY' if order.isbuy() else '決済SELL'}\n"
                        f"決済数量: {order.executed.size:.2f}\n"
                        f"決済価格: {order.executed.price:.2f}\n"
                        f"実現損益: {pnl:,.2f}")
                self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
                self.sl_price, self.tp_price = 0.0, 0.0

            self._send_notification(subject, body)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.data0._name})"
            body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\n"
                    f"銘柄: {self.data0._name}\n"
                    f"ステータス: {order.getstatusname()}")
            self.log(f"注文失敗/キャンセル: {order.getstatusname()}")
            self._send_notification(subject, body)
            if is_entry: self.sl_price, self.tp_price = 0.0, 0.0

        if is_entry: self.entry_order = None
        if is_exit: self.exit_orders = []

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
        sl_cond = exit_conditions.get('stop_loss', {}); tp_cond = exit_conditions.get('take_profit', {})
        is_long, size = self.getposition().size > 0, abs(self.getposition().size)
        limit_order, stop_order = None, None

        if tp_cond and self.tp_price != 0:
            limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False)
            self.log(f"利確(Limit)注文を作成: Price={self.tp_price:.2f}")

        if sl_cond and sl_cond.get('type') == 'atr_stoptrail':
            stop_order = self.sell(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order) if is_long else self.buy(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order)
            self.log(f"損切(StopTrail)注文をOCOで発注: TrailAmount={self.risk_per_share:.2f}")

        self.exit_orders = [o for o in [limit_order, stop_order] if o is not None]

    def _check_live_exit_conditions(self):
        pos = self.getposition()
        is_long = pos.size > 0
        current_price = self.data.close[0]

        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            self.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            self.exit_orders.append(self.close()); return

        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                self.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                self.exit_orders.append(self.close()); return

            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                self.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                self.sl_price = new_sl_price

    def _check_entry_conditions(self):
        exit_conditions = self.strategy_params['exit_conditions']
        sl_cond = exit_conditions['stop_loss']
        atr_key = self._get_indicator_key(sl_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in sl_cond.get('params', {}).items() if k!='multiplier'})

        atr_indicator = self.indicators.get(atr_key)
        if not atr_indicator or len(atr_indicator) == 0:
            self.logger.debug(f"ATRインジケーター '{atr_key}' が未計算のためスキップします。")
            return

        atr_val = atr_indicator[0]
        if not atr_val or atr_val <= 1e-9: return
        self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)

        if self.risk_per_share < 1e-9: self.log(f"計算されたリスクが0のため、エントリーをスキップします。ATR: {atr_val}"); return

        entry_price = self.data_feeds['short'].close[0]
        sizing = self.strategy_params.get('sizing', {})
        size = min((self.broker.getcash()*sizing.get('risk_per_trade',0.01))/self.risk_per_share,
                   sizing.get('max_investment_per_trade', 10000000)/entry_price if entry_price>0 else float('inf'))
        if size <= 0: return

        def place_order(trade_type, reason):
            self.entry_reason, is_long = reason, trade_type == 'long'
            self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share

            tp_cond = exit_conditions.get('take_profit')
            if tp_cond:
                tp_key = self._get_indicator_key(tp_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in tp_cond.get('params', {}).items() if k!='multiplier'})
                tp_atr_indicator = self.indicators.get(tp_key)
                if not tp_atr_indicator or len(tp_atr_indicator) == 0:
                    self.log(f"利確用のATRインジケーター '{tp_key}' が未計算です。"); self.tp_price = 0
                else:
                    tp_atr_val = tp_atr_indicator[0]
                    if not tp_atr_val or tp_atr_val <= 1e-9: self.tp_price = 0
                    else:
                        tp_multiplier = tp_cond.get('params', {}).get('multiplier', 5.0)
                        self.tp_price = entry_price + tp_atr_val * tp_multiplier if is_long else entry_price - tp_atr_val * tp_multiplier

            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, TP: {self.tp_price:.2f}, SL: {self.sl_price:.2f}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)

            subject = f"【リアルタイム取引】新規注文発注 ({self.data0._name})"
            body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\n"
                    f"銘柄: {self.data0._name}\n"
                    f"戦略: {self.strategy_params.get('strategy_name', 'N/A')}\n"
                    f"方向: {'BUY' if is_long else 'SELL'}\n"
                    f"数量: {size:.2f}\n\n"
                    "--- エントリー根拠詳細 ---\n"
                    f"{self.entry_reason}")
            self._send_notification(subject, body)

        trading_mode = self.strategy_params.get('trading_mode', {})
        if trading_mode.get('long_enabled', True):
            met, reason = self._check_all_conditions('long')
            if met: place_order('long', reason); return
        if not self.entry_order and trading_mode.get('short_enabled', True):
            met, reason = self._check_all_conditions('short')
            if met: place_order('short', reason)

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
            return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), 'atr', atr_params)

    def _recalculate_exit_prices(self, entry_price, is_long):
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss'); tp_cond = exit_conditions.get('take_profit')
        self.sl_price, self.tp_price, self.risk_per_share = 0.0, 0.0, 0.0

        if sl_cond:
            sl_atr_key = self._get_atr_key_for_exit('stop_loss')
            sl_atr_indicator = self.indicators.get(sl_atr_key)
            if sl_atr_indicator and len(sl_atr_indicator) > 0:
                atr_val = sl_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    self.risk_per_share = atr_val * sl_cond['params']['multiplier']
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
        if tp_cond:
            tp_atr_key = self._get_atr_key_for_exit('take_profit')
            tp_atr_indicator = self.indicators.get(tp_atr_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                atr_val = tp_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    self.tp_price = entry_price + (atr_val * tp_cond['params']['multiplier']) if is_long else entry_price - (atr_val * tp_cond['params']['multiplier'])

    def _restore_position_state(self):
        pos_info = self.p.persisted_position
        size, price = pos_info['size'], pos_info['price']

        self.position.size = size
        self.position.price = price
        self.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])

        self._recalculate_exit_prices(entry_price=price, is_long=(size > 0))
        self.log(f"ポジション復元完了。Size: {self.position.size}, Price: {self.position.price}, SL: {self.sl_price:.2f}, TP: {self.tp_price:.2f}")

    def next(self):
        if self.logger.isEnabledFor(logging.DEBUG):
            log_msg = f"\n===== Bar Check on {self.data.datetime.datetime(0).isoformat()} =====\n"
            log_msg += "--- Price Data ---\n"
            for tf_name, data_feed in self.data_feeds.items():
                if len(data_feed) > 0 and data_feed.close[0] is not None:
                    dt = data_feed.datetime.datetime(0)
                    log_msg += (f"  [{tf_name.upper():<6}] {dt.isoformat()} | "
                                f"O:{data_feed.open[0]:.2f} H:{data_feed.high[0]:.2f} "
                                f"L:{data_feed.low[0]:.2f} C:{data_feed.close[0]:.2f} "
                                f"V:{data_feed.volume[0]:.0f}\n")
                else:
                    log_msg += f"  [{tf_name.upper():<6}] No data available for this bar\n"
            log_msg += "--- Indicator Values ---\n"
            sorted_indicator_keys = sorted(self.indicators.keys())
            for key in sorted_indicator_keys:
                indicator = self.indicators[key]
                if len(indicator) > 0 and indicator[0] is not None:
                    values = []
                    for line_name in indicator.lines.getlinealiases():
                        line = getattr(indicator.lines, line_name)
                        if len(line) > 0 and line[0] is not None:
                            values.append(f"{line_name}: {line[0]:.4f}")
                    if values:
                        log_msg += f"  [{key}]: {', '.join(values)}\n"
                    else:
                        log_msg += f"  [{key}]: Value not ready\n"
                else:
                    log_msg += f"  [{key}]: Not calculated yet\n"
            self.logger.debug(log_msg)

        if len(self.data) == 0 or not self.live_trading_started or self.data.volume[0] == 0:
            return

        if self.is_restoring:
            try:
                atr_key = self._get_atr_key_for_exit('stop_loss')
                if atr_key and self.indicators.get(atr_key) and len(self.indicators.get(atr_key)) > 0:
                    self._restore_position_state()
                    self.is_restoring = False
                else:
                    self.log("ポジション復元待機中: インジケーターが未計算です...")
                    return
            except Exception as e:
                self.log(f"ポジションの復元中にクリティカルエラーが発生: {e}", level=logging.CRITICAL)
                self.is_restoring = False
                return

        if self.entry_order or (self.live_trading and self.exit_orders):
            return

        if self.getposition().size:
            if self.live_trading: self._check_live_exit_conditions()
            return

        self._check_entry_conditions()

    def log(self, txt, dt=None, level=logging.INFO):
        log_time = dt or self.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')
        if level >= logging.CRITICAL:
            subject = f"【リアルタイム取引】システム警告 ({self.data0._name})"
            self._send_notification(subject, txt)