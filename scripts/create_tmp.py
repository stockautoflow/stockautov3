import os

# ==============================================================================
# ファイル: create_tmp.py
# 説明:
#   詳細設計書に基づき、src/core/strategy.py を修正します。
#   - 修正点1: check_entry_conditions内で、注文前にSL/TP計算を実行。
#   - 修正点2: notify_order内の冗長なSL/TP計算を削除。
# 実行方法: python create_tmp.py
# ==============================================================================

project_files = {
    "src/core/strategy.py": """import backtrader as bt
import logging
import inspect
import yaml
import copy
import threading
from datetime import datetime, timedelta
from .indicators import SafeStochastic, VWAP, SafeADX
from .util import notifier

class DynamicStrategy(bt.Strategy):
    params = (
        ('strategy_params', None),
        ('live_trading', False),
        ('persisted_position', None),
    )

    def __init__(self):
        super().__init__()

        self.live_trading = self.p.live_trading
        symbol_str = self.data0._name.split('_')[0]
        self.logger = logging.getLogger(f"{self.__class__.__name__}-{symbol_str}")

        self.bridge = self.broker.bridge if hasattr(self.broker, 'bridge') else None
        if self.bridge:
            self.logger.info("ExcelBridgeへの参照を確立しました。")

        if self.p.strategy_params:
            self.strategy_params = self.p.strategy_params
        else:
            raise ValueError("戦略パラメータ(strategy_params)が渡されていません。")

        if not isinstance(self.strategy_params.get('exit_conditions'), dict):
            raise ValueError(f"戦略 '{self.strategy_params.get('name', 'N/A')}' に exit_conditions が定義されていません。")
        if not isinstance(self.strategy_params.get('exit_conditions', {}).get('stop_loss'), dict):
            raise ValueError(f"戦略 '{self.strategy_params.get('name', 'N/A')}' の exit_conditions に stop_loss が定義されていません。")

        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self.create_indicators()
        self.entry_order = None
        self.exit_orders = []
        self.entry_reason = ""
        self.entry_reason_for_trade = ""
        self.executed_size = 0
        self.risk_per_share = 0.0
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.current_position_entry_dt = None
        
        self.live_data_started = False
        self.is_restoring = self.p.persisted_position is not None

    def next(self):
        if len(self.data) == 0 or self.data.close[0] <= 0:
            return
        
        if not self.live_data_started and hasattr(self.broker, 'live_data_started') and self.broker.live_data_started:
            self.live_data_started = True
            self.logger.info("リアルタイムデータフェーズに移行。実ポジションとの同期を開始します。")

        if self.live_data_started:
            if self.bridge is None: return

            symbol = self.data0._name
            held_positions = self.bridge.get_held_positions()
            is_pos_in_excel = symbol in held_positions
            is_pos_in_bt = self.getposition().size != 0

            if is_pos_in_excel and not is_pos_in_bt:
                entry_price = held_positions[symbol]
                self.log(f"Excel上の新規ポジションを検知。銘柄: {symbol}, 建値: {entry_price:.2f}")
                self.recalculate_exit_prices(entry_price=entry_price, is_long=True)
                self.buy(size=100)
                self.log(f"決済監視を開始。TP: {self.tp_price:.2f}, SL: {self.sl_price:.2f}")
                return
            elif not is_pos_in_excel and is_pos_in_bt:
                self.log(f"Excel上のポジション決済を検知。銘柄: {symbol}。内部状態をリセットします。")
                self.close()
                self.sl_price, self.tp_price = 0.0, 0.0
                return
            
            if is_pos_in_bt:
                self.check_live_exit_conditions()
            else:
                if not self.entry_order: self.check_entry_conditions()
            return

        if self.is_restoring:
            try:
                atr_key = self.get_atr_key_for_exit('stop_loss')
                if atr_key and self.indicators.get(atr_key) and len(self.indicators.get(atr_key)) > 0:
                    self.restore_position_state()
                    self.is_restoring = False
                else:
                    self.log("ポジション復元待機中: インジケーターが未計算です...")
                    return
            except Exception as e:
                self.log(f"ポジションの復元中にクリティカルエラーが発生: {e}", level=logging.CRITICAL)
                self.is_restoring = False
                return

        if self.entry_order: return

        if not self.getposition().size:
            self.check_entry_conditions()

    def start(self):
        pass

    def get_indicator_key(self, timeframe, name, params=None):
        if params is None:
            params = {}
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def evaluate_condition(self, cond):
        tf, cond_type = cond['timeframe'], cond.get('type')
        data_feed = self.data_feeds[tf]
        if len(data_feed) == 0:
            return False, ""

        if cond_type in ['crossover', 'crossunder']:
            k1 = self.get_indicator_key(tf, **cond['indicator1'])
            k2 = self.get_indicator_key(tf, **cond['indicator2'])
            cross_indicator = self.indicators.get(f"cross_{k1}_vs_{k2}")
            if cross_indicator is None or len(cross_indicator) == 0: return False, ""

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or \\
                     (cross_indicator[0] < 0 and cond_type == 'crossunder')

            p1_val = cond['indicator1'].get('params')
            p1_str = ",".join(map(str, p1_val.values())) if isinstance(p1_val, dict) else ""
            
            p2_val = cond['indicator2'].get('params')
            p2_str = ",".join(map(str, p2_val.values())) if isinstance(p2_val, dict) else ""
            
            reason = f"{tf[0].upper()}: {cond_type}({cond['indicator1']['name']}({p1_str}),{cond['indicator2']['name']}({p2_str})) [{is_met}]"
            return is_met, reason

        ind = self.indicators.get(self.get_indicator_key(tf, **cond['indicator']))
        if ind is None or len(ind) == 0: return False, ""

        val, compare, target = ind[0], cond['compare'], cond['target']
        target_type, target_val = target.get('type'), None
        target_val_str = ""

        if target_type == 'data':
            target_val = getattr(data_feed, target['value'])[0]
            target_val_str = f"{target['value']} [{target_val:.2f}]"
        elif target_type == 'indicator':
            target_ind = self.indicators.get(self.get_indicator_key(tf, **target['indicator']))
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

        params_val = cond['indicator'].get('params')
        if isinstance(params_val, dict):
            params_str = ",".join(map(str, params_val.values()))
        else:
            params_str = ""

        reason = f"{tf[0].upper()}: {cond['indicator']['name']}({params_str}) [{val:.2f}] {compare} {target_val_str}"
        return is_met, reason

    def send_notification(self, subject, body, immediate=False):
        if not self.live_trading: return
        bar_datetime = self.data0.datetime.datetime(0)
        if bar_datetime.tzinfo is not None: bar_datetime = bar_datetime.replace(tzinfo=None)
        if datetime.now() - bar_datetime > timedelta(minutes=5):
            self.logger.debug(f"過去データに基づく通知を抑制: {subject} (データ時刻: {bar_datetime})")
            return
        self.logger.debug(f"通知リクエストを発行: {subject} (Immediate: {immediate})")
        notifier.send_email(subject, body, immediate=immediate)

    def create_indicators(self):
        indicators, unique_defs = {}, {}
        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            key = self.get_indicator_key(timeframe, **ind_def)
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
            name = ind_def.get('name')
            params = ind_def.get('params', {})
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
                    k1 = self.get_indicator_key(cond['timeframe'], **cond['indicator1']); k2 = self.get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    if k1 in indicators and k2 in indicators:
                        cross_key = f"cross_{k1}_vs_{k2}"
                        if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2], plot=False)
        return indicators

    def check_all_conditions(self, trade_type):
        conditions = self.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions: return False, ""

        reason_details = []
        all_conditions_met = True
        for c in conditions:
            is_met, reason_str = self.evaluate_condition(c)
            if not is_met:
                all_conditions_met = False
                break
            reason_details.append(reason_str)

        if all_conditions_met:
            return True, " / ".join(reason_details)
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
                body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\\n"
                        f"銘柄: {self.data0._name}\\n"
                        f"ステータス: {order.getstatusname()}\\n"
                        f"方向: {'BUY' if order.isbuy() else 'SELL'}\\n"
                        f"約定数量: {order.executed.size:.2f}\\n"
                        f"約定価格: {order.executed.price:.2f}")
                self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
                
                if not self.live_trading:
                    self.place_native_exit_orders()
                else:
                    # ### ▼▼▼ 修正箇所2 ▼▼▼ ###
                    # 冗長なSL/TP再計算ロジックを削除
                    self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, SL={self.sl_price:.2f}")

                self.send_notification(subject, body, immediate=True)

            elif is_exit:
                pnl = order.executed.pnl
                exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
                subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.data0._name})"
                body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\\n"
                        f"銘柄: {self.data0._name}\\n"
                        f"ステータス: {order.getstatusname()} ({exit_reason})\\n"
                        f"方向: {'決済BUY' if order.isbuy() else '決済SELL'}\\n"
                        f"決済数量: {order.executed.size:.2f}\\n"
                        f"決済価格: {order.executed.price:.2f}\\n"
                        f"実現損益: {pnl:,.2f}")
                self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
                self.sl_price, self.tp_price = 0.0, 0.0
                self.send_notification(subject, body, immediate=True)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.data0._name})"
            body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\\n"
                    f"銘柄: {self.data0._name}\\n"
                    f"ステータス: {order.getstatusname()}")
            self.log(f"注文失敗/キャンセル: {order.getstatusname()}")
            self.send_notification(subject, body, immediate=True)
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

    def place_native_exit_orders(self):
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

    def check_live_exit_conditions(self):
        pos = self.getposition()
        if not pos.size: return
        
        is_long = pos.size > 0
        current_price = self.data.close[0]

        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            self.log(f"ライブ: ★★★利確シグナル★★★ 現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            subject = f"【リアルタイム取引】利確シグナル ({self.data0._name})"
            body = f"TP価格 {self.tp_price:.2f} に到達しました。現在価格: {current_price:.2f}"
            self.send_notification(subject, body, immediate=True)
            return

        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                self.log(f"ライブ: ★★★損切りシグナル★★★ 現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                subject = f"【リアルタイム取引】損切りシグナル ({self.data0._name})"
                body = f"SL価格 {self.sl_price:.2f} に到達しました。現在価格: {current_price:.2f}"
                self.send_notification(subject, body, immediate=True)
                return

            sl_cond = self.strategy_params.get('exit_conditions', {}).get('stop_loss', {})
            if sl_cond.get('type') == 'atr_stoptrail':
                new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
                if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                    self.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                    self.sl_price = new_sl_price

    def check_entry_conditions(self):
        if self.live_data_started:
            if self.data0._name in self.bridge.get_held_positions():
                return

        exit_conditions = self.strategy_params['exit_conditions']
        sl_cond = exit_conditions['stop_loss']
        atr_key = self.get_atr_key_for_exit('stop_loss')
        if not atr_key: return
        
        atr_indicator = self.indicators.get(atr_key)
        if not atr_indicator or len(atr_indicator) == 0:
            self.logger.debug(f"ATRインジケーター '{atr_key}' が未計算のためスキップします。")
            return

        atr_val = atr_indicator[0]
        if not atr_val or atr_val <= 1e-9: return

        entry_price = self.data_feeds['short'].close[0]
        sizing = self.strategy_params.get('sizing', {})
        self.risk_per_share = atr_val * sl_cond['params']['multiplier']
        if self.risk_per_share < 1e-9: self.log(f"計算されたリスクが0のため、エントリーをスキップします。ATR: {atr_val}"); return
        
        size = min((self.broker.getcash()*sizing.get('risk_per_trade',0.01))/self.risk_per_share,
                   sizing.get('max_investment_per_trade', 10000000)/entry_price if entry_price>0 else float('inf'))
        if size <= 0: return

        def place_order(trade_type, reason):
            self.entry_reason = reason
            is_long = trade_type == 'long'
            
            # ### ▼▼▼ 修正箇所1 ▼▼▼ ###
            # 注文前にSL/TP価格を計算する
            self.recalculate_exit_prices(entry_price, is_long)

            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)

            subject = f"【リアルタイム取引】新規注文シグナル ({self.data0._name})"
            body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\\n"
                    f"銘柄: {self.data0._name}\\n"
                    f"方向: {'BUY' if is_long else 'SELL'}\\n"
                    f"数量: {size:.2f}\\n\\n"
                    "--- エントリー根拠 ---\\n"
                    f"{self.entry_reason}")
            self.send_notification(subject, body, immediate=True)

        trading_mode = self.strategy_params.get('trading_mode', {})
        if trading_mode.get('long_enabled', True):
            met, reason = self.check_all_conditions('long')
            if met: place_order('long', reason); return
        if not self.entry_order and trading_mode.get('short_enabled', True):
            met, reason = self.check_all_conditions('short')
            if met: place_order('short', reason)

    def get_atr_key_for_exit(self, exit_type):
        try:
            exit_conditions = self.strategy_params['exit_conditions']
            if not exit_conditions or exit_type not in exit_conditions: return None

            exit_cond = exit_conditions[exit_type]
            if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
                return None
            
            params = exit_cond['params']
            if not isinstance(params, dict):
                self.logger.error(f"exit_cond['params']が辞書ではありません: {params}")
                return None
            
            atr_params = {k: v for k, v in params.items() if k != 'multiplier'}
            timeframe = exit_cond.get('timeframe', 'short')
            return self.get_indicator_key(timeframe, 'atr', atr_params)
        except KeyError as e:
            self.logger.error(f"戦略パラメータ内に予期したキーが見つかりません: {e}")
            self.logger.error(f"現在のexit_conditions: {self.strategy_params.get('exit_conditions')}")
            return None

    def recalculate_exit_prices(self, entry_price, is_long):
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss'); tp_cond = exit_conditions.get('take_profit')
        self.sl_price, self.tp_price, self.risk_per_share = 0.0, 0.0, 0.0

        sl_atr_key = self.get_atr_key_for_exit('stop_loss')
        if sl_cond and sl_atr_key:
            sl_atr_indicator = self.indicators.get(sl_atr_key)
            if sl_atr_indicator and len(sl_atr_indicator) > 0:
                atr_val = sl_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    self.risk_per_share = atr_val * sl_cond['params']['multiplier']
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
        
        tp_atr_key = self.get_atr_key_for_exit('take_profit')
        if tp_cond and tp_atr_key:
            tp_atr_indicator = self.indicators.get(tp_atr_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                atr_val = tp_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    self.tp_price = entry_price + (atr_val * tp_cond['params']['multiplier']) if is_long else entry_price - (atr_val * tp_cond['params']['multiplier'])

    def restore_position_state(self):
        pos_info = self.p.persisted_position
        size, price = pos_info['size'], pos_info['price']
        self.position.size = size
        self.position.price = price
        self.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])
        self.recalculate_exit_prices(entry_price=price, is_long=(size > 0))
        self.log(f"ポジション復元完了。Size: {self.position.size}, Price: {self.position.price}, SL: {self.sl_price:.2f}, TP: {self.tp_price:.2f}")

    def log(self, txt, dt=None, level=logging.INFO):
        log_time = dt or self.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')
        if level >= logging.CRITICAL:
            subject = f"【リアルタイム取引】システム警告 ({self.data0._name})"
            self.send_notification(subject, txt, immediate=False)
""",
}

def create_files(files_dict):
    """
    辞書からファイル名と内容を読み取り、ファイルを作成する。
    """
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"  - ファイル作成: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- 修正版 core パッケージの生成を開始します ---")
    create_files(project_files)
    print("--- core パッケージの生成が完了しました ---")
    print("\n次のステップ:")
    print("1. このスクリプト(create_tmp.py)をプロジェクトルートで実行してください。")
    print("2. src/core/strategy.py が更新されたことを確認してください。")
    print("3. 再度バックテストを実行し、結果を確認してください。")