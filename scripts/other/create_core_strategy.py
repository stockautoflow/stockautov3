import os

project_files = {
    "src/core/strategy_initializer.py": """
import yaml
import copy
import logging
import inspect
import backtrader as bt
from ..indicators import SafeStochastic, VWAP, SafeADX

logger = logging.getLogger(__name__)

class StrategyInitializer:
    def __init__(self, strategy_catalog_file, base_strategy_file):
        self.strategy_catalog = self._load_yaml(strategy_catalog_file)
        self.base_strategy_params = self._load_yaml(base_strategy_file)

    def _load_yaml(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"設定ファイル '{filepath}' が見つかりません。")
            return {}
        except Exception as e:
            logger.error(f"'{filepath}' の読み込み中にエラー: {e}")
            return {}

    def initialize(self, strategy, symbol, live_trading=False, persisted_position=None):
        strategy.live_trading = live_trading
        
        # 戦略パラメータの動的ロード
        strategy_name = strategy.p.strategy_assignments.get(str(symbol))
        if not strategy_name:
            if not live_trading: logger.warning(f"銘柄 {symbol} に戦略が割り当てられていません。")
            strategy.strategy_params = copy.deepcopy(self.base_strategy_params)
        else:
            entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
            if not entry_strategy_def: 
                logger.error(f"エントリー戦略カタログに '{strategy_name}' が見つかりません。")
                strategy.strategy_params = copy.deepcopy(self.base_strategy_params)
            else:
                strategy.strategy_params = copy.deepcopy(self.base_strategy_params)
                strategy.strategy_params.update(entry_strategy_def)
        
        strategy.logger = logging.getLogger(f"{strategy.__class__.__name__}-{symbol}")
        strategy.indicators = self.create_indicators(strategy, strategy.strategy_params)
        
        # 永続化ポジションの復元待機フラグ
        strategy.is_restoring = persisted_position is not None

    def create_indicators(self, strategy, strategy_params):
        indicators, unique_defs = {}, {}
        
        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            params = ind_def.get('params', {})
            param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
            key = f"{timeframe}_{ind_def['name']}_{param_str}"
            if key not in unique_defs: unique_defs[key] = (timeframe, ind_def)

        if isinstance(strategy_params.get('entry_conditions'), dict):
            for cond_list in strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe')
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target']['indicator'])

        if isinstance(strategy_params.get('exit_conditions'), dict):
            for exit_type in ['take_profit', 'stop_loss']:
                cond = strategy_params['exit_conditions'].get(exit_type, {})
                if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                    atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                    add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})

        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = None
            
            if name.lower() == 'stochastic': ind_cls = SafeStochastic
            elif name.lower() == 'vwap': ind_cls = VWAP
            elif name.lower() == 'adx': ind_cls = SafeADX
            else:
                cls_candidate = getattr(bt.indicators, name, None)
                if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                    ind_cls = cls_candidate
            
            if ind_cls:
                indicators[key] = ind_cls(strategy.data_feeds[timeframe], plot=False, **params)
            else:
                strategy.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        for cond_list in strategy_params.get('entry_conditions', {}).values():
            for cond in cond_list:
                if cond.get('type') in ['crossover', 'crossunder']:
                    k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1'])
                    k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    cross_key = f"cross_{k1}_vs_{k2}"
                    if k1 in indicators and k2 in indicators and cross_key not in indicators:
                        indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2], plot=False)

        return indicators

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"
""",
    "src/core/trade_evaluator.py": """
import backtrader as bt
import logging
from datetime import datetime
import copy

logger = logging.getLogger(__name__)

class TradeEvaluator:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators
        self.entry_reason = ""
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.risk_per_share = 0.0

    def _evaluate_single_condition(self, cond):
        tf, cond_type = cond['timeframe'], cond.get('type')
        data_feed = self.data_feeds[tf]
        if len(data_feed) == 0:
            return False, "データなし"

        if cond_type in ['crossover', 'crossunder']:
            k1 = self._get_indicator_key(tf, **cond['indicator1'])
            k2 = self._get_indicator_key(tf, **cond['indicator2'])
            cross_indicator = self.indicators.get(f"cross_{k1}_vs_{k2}")
            if cross_indicator is None or len(cross_indicator) == 0: return False, "インジケーター未計算"

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or \\
                     (cross_indicator[0] < 0 and cond_type == 'crossunder')

            p1 = ",".join(map(str, cond['indicator1'].get('params', {}).values()))
            p2 = ",".join(map(str, cond['indicator2'].get('params', {}).values()))
            reason = f"{tf[0].upper()}: {cond_type}({cond['indicator1']['name']}({p1}),{cond['indicator2']['name']}({p2})) [{is_met}]"
            return is_met, reason

        ind_key = self._get_indicator_key(tf, **cond['indicator'])
        ind = self.indicators.get(ind_key)
        if ind is None or len(ind) == 0: return False, "インジケーター未計算"

        val, compare, target = ind[0], cond['compare'], cond['target']
        target_type, target_val = target.get('type'), None
        target_val_str = ""

        if target_type == 'data':
            if not hasattr(data_feed, target['value']): return False, f"データライン '{target['value']}' が見つかりません。"
            target_val = getattr(data_feed, target['value'])[0]
            target_val_str = f"{target['value']} [{target_val:.2f}]"
        elif target_type == 'indicator':
            target_ind_key = self._get_indicator_key(tf, **target['indicator'])
            target_ind = self.indicators.get(target_ind_key)
            if target_ind is None or len(target_ind) == 0: return False, "ターゲットインジケーター未計算"
            target_val = target_ind[0]
            target_val_str = f"{target['indicator']['name']}(...) [{target_val:.2f}]"
        elif target_type == 'values':
            target_val = target['value']
            if compare == 'between': target_val_str = f"[{target_val[0]},{target_val[1]}]"
            else: target_val_str = f"[{target_val}]"

        if target_val is None: return False, "ターゲット値なし"

        is_met = False
        if compare == '>':
            is_met = val > target_val[0] if isinstance(target_val, list) else val > target_val
        elif compare == '<':
            is_met = val < target_val[0] if isinstance(target_val, list) else val < target_val
        elif compare == 'between':
            is_met = target_val[0] < val < target_val[1]

        params_str = ",".join(map(str, cond['indicator'].get('params', {}).values()))
        reason = f"{tf[0].upper()}: {cond['indicator']['name']}({params_str}) [{val:.2f}] {compare} {target_val_str} ({is_met})"
        return is_met, reason

    def evaluate_entry_conditions(self):
        trading_mode = self.strategy_params.get('trading_mode', {})
        
        if trading_mode.get('long_enabled', True):
            conditions = self.strategy_params.get('entry_conditions', {}).get('long', [])
            if conditions and all(self._evaluate_single_condition(c)[0] for c in conditions):
                self.entry_reason = " / ".join([self._evaluate_single_condition(c)[1] for c in conditions])
                return 'long'
        
        if trading_mode.get('short_enabled', True):
            conditions = self.strategy_params.get('entry_conditions', {}).get('short', [])
            if conditions and all(self._evaluate_single_condition(c)[0] for c in conditions):
                self.entry_reason = " / ".join([self._evaluate_single_condition(c)[1] for c in conditions])
                return 'short'
        
        return None

    def evaluate_exit_conditions(self, current_price, is_long):
        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            logger.info(f"決済条件ヒット: 利確。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            return 'take_profit'

        if self.sl_price != 0 and ((is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price)):
            logger.info(f"決済条件ヒット: 損切り。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
            return 'stop_loss'

        # トレールストップの更新
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss', {})
        if sl_cond and sl_cond.get('type') == 'atr_stoptrail':
            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                self.sl_price = new_sl_price
                logger.info(f"損切り価格を更新: {self.sl_price:.2f} -> {new_sl_price:.2f}")

        return None
        
    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"
""",
    "src/core/order_executor.py": """
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

        # strategyインスタンスに状態を保存
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
""",
    "src/core/position_manager.py": """
import logging
from datetime import datetime
import copy

logger = logging.getLogger(__name__)

class PositionManager:
    def __init__(self, strategy_params, data_feeds, indicators):
        self.strategy_params = strategy_params
        self.data_feeds = data_feeds
        self.indicators = indicators
        
    def restore_state(self, strategy, persisted_position):
        pos_info = persisted_position
        size, price = pos_info['size'], pos_info['price']
        
        strategy.position.size = size
        strategy.position.price = price
        strategy.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])
        
        self._recalculate_exit_prices(strategy, entry_price=price, is_long=(size > 0))
        logger.info(f"ポジション復元完了。Size: {strategy.position.size}, Price: {strategy.position.price}, SL: {strategy.sl_price:.2f}, TP: {strategy.tp_price:.2f}")

    def _recalculate_exit_prices(self, strategy, entry_price, is_long):
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss')
        tp_cond = exit_conditions.get('take_profit')
        strategy.sl_price, strategy.tp_price, strategy.risk_per_share = 0.0, 0.0, 0.0

        if sl_cond:
            sl_atr_key = self._get_atr_key_for_exit('stop_loss')
            sl_atr_indicator = self.indicators.get(sl_atr_key)
            if sl_atr_indicator and len(sl_atr_indicator) > 0:
                atr_val = sl_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    strategy.risk_per_share = atr_val * sl_cond['params']['multiplier']
                    strategy.sl_price = entry_price - strategy.risk_per_share if is_long else entry_price + strategy.risk_per_share

        if tp_cond:
            tp_atr_key = self._get_atr_key_for_exit('take_profit')
            tp_atr_indicator = self.indicators.get(tp_atr_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                atr_val = tp_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    strategy.tp_price = entry_price + (atr_val * tp_cond['params']['multiplier']) if is_long else entry_price - (atr_val * tp_cond['params']['multiplier'])

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
            return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), 'atr', atr_params)

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"
""",
    "src/core/notification_manager.py": """
import logging
from datetime import datetime, timedelta
from ..util import notifier

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, live_trading, notifier_instance):
        self.live_trading = live_trading
        self.notifier = notifier_instance
        self.symbol_str = ""

    def handle_order_notification(self, order, data_feed):
        self.symbol_str = data_feed._name.split('_')[0]
        is_entry = order.info.get('is_entry')
        is_exit = order.info.get('is_exit')
        
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if not is_entry and not is_exit:
            return

        subject = ""
        body = ""
        is_immediate = False

        if order.status == order.Completed:
            if is_entry:
                subject = f"【リアルタイム取引】エントリー注文約定 ({self.symbol_str})"
                body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\\n"
                        f"銘柄: {self.symbol_str}\\n"
                        f"ステータス: {order.getstatusname()}\\n"
                        f"方向: {'BUY' if order.isbuy() else 'SELL'}\\n"
                        f"約定数量: {order.executed.size:.2f}\\n"
                        f"約定価格: {order.executed.price:.2f}")
                is_immediate = True
            elif is_exit:
                pnl = order.executed.pnl
                exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
                subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.symbol_str})"
                body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\\n"
                        f"銘柄: {self.symbol_str}\\n"
                        f"ステータス: {order.getstatusname()} ({exit_reason})\\n"
                        f"方向: {'決済BUY' if order.isbuy() else '決済SELL'}\\n"
                        f"決済数量: {order.executed.size:.2f}\\n"
                        f"決済価格: {order.executed.price:.2f}\\n"
                        f"実現損益: {pnl:,.2f}")
                is_immediate = True
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.symbol_str})"
            body = (f"日時: {data_feed.datetime.datetime(0).isoformat()}\\n"
                    f"銘柄: {self.symbol_str}\\n"
                    f"ステータス: {order.getstatusname()}\\n"
                    f"詳細: {order.info.get('reason', 'N/A')}")
            is_immediate = True

        if subject and body:
            self._send_notification(subject, body, is_immediate)

    def log_trade_event(self, trade, logger_instance):
        if trade.isopen:
            logger_instance.info(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
        elif trade.isclosed:
            logger_instance.info(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")

    def _send_notification(self, subject, body, immediate=False):
        if not self.live_trading:
            return

        bar_datetime = datetime.now()
        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)

        if datetime.now() - bar_datetime > timedelta(minutes=5):
            logger.debug(f"過去データに基づく通知を抑制: {subject} (データ時刻: {bar_datetime})")
            return

        logger.debug(f"通知リクエストを発行: {subject} (Immediate: {immediate})")
        notifier.send_email(subject, body, immediate=immediate)
""",
    "src/core/strategy.py": """
import backtrader as bt
import logging
import copy
from datetime import datetime, timedelta

from . import strategy_initializer
from . import trade_evaluator
from . import order_executor
from . import position_manager
from . import notification_manager
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
        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = {}
        self.strategy_params = {}
        self.live_trading = self.p.live_trading
        
        # モジュールインスタンスの初期化
        self.initializer = strategy_initializer.StrategyInitializer('config/strategy_catalog.yml', 'config/strategy_base.yml')
        
        symbol_str = self.data0._name.split('_')[0]
        self.initializer.initialize(self, symbol_str, self.live_trading, self.p.persisted_position)
        
        self.evaluator = trade_evaluator.TradeEvaluator(self.strategy_params, self.data_feeds, self.indicators)
        self.executor = order_executor.OrderExecutor(self.strategy_params, self.data_feeds, self.indicators)
        self.pos_manager = position_manager.PositionManager(self.strategy_params, self.data_feeds, self.indicators)
        self.notif_manager = notification_manager.NotificationManager(self.live_trading, notifier)
        
        # 戦略の内部状態
        self.entry_order = None
        self.exit_orders = []
        self.entry_reason = ""
        self.executed_size = 0
        self.risk_per_share = 0.0
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.current_position_entry_dt = None
        self.live_trading_started = False
        
        self.is_restoring = self.p.persisted_position is not None

    def start(self):
        self.live_trading_started = True

    def notify_order(self, order):
        self.notif_manager.handle_order_notification(order, self.data0)
        
        is_entry = order.info.get('is_entry')
        is_exit = order.info.get('is_exit')
        
        if order.status == order.Completed:
            if is_entry:
                if not self.live_trading:
                    self.exit_orders = self.executor.place_exit_orders(self, self.live_trading, "Backtest")
                
                self.executed_size = order.executed.size
                self.entry_reason_for_trade = self.entry_reason
            
            if is_exit:
                self.sl_price, self.tp_price = 0.0, 0.0

        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            if is_entry:
                self.sl_price, self.tp_price = 0.0, 0.0
        
        if is_entry: self.entry_order = None
        if is_exit: self.exit_orders = []
        
    def notify_trade(self, trade):
        self.notif_manager.log_trade_event(trade, self.logger)
        if trade.isopen:
            self.current_position_entry_dt = self.data.datetime.datetime(0)
            self.executed_size = trade.size
            self.entry_reason_for_trade = self.entry_reason
        elif trade.isclosed:
            trade.executed_size = self.executed_size
            trade.entry_reason_for_trade = self.entry_reason_for_trade
            self.current_position_entry_dt, self.executed_size = None, 0
            self.entry_reason, self.entry_reason_for_trade = "", ""
    
    def next(self):
        if self.logger.isEnabledFor(logging.DEBUG):
            self._log_debug_info()
        
        if len(self.data) == 0 or not self.live_trading_started or self.data.volume[0] == 0:
            return

        if self.is_restoring:
            if not self.evaluator._get_atr_key_for_exit('stop_loss') or len(self.indicators.get(self.evaluator._get_atr_key_for_exit('stop_loss'))) > 0:
                self.pos_manager.restore_state(self, self.p.persisted_position)
                self.is_restoring = False
            else:
                self.logger.info("ポジション復元待機中: インジケーターが未計算です...")
                return

        if self.entry_order or (self.live_trading and self.exit_orders):
            return

        pos_size = self.getposition().size
        if pos_size:
            if self.live_trading:
                exit_reason = self.evaluator.evaluate_exit_conditions(self.data.close[0], pos_size > 0)
                if exit_reason:
                    self.exit_orders.append(self.executor.place_exit_orders(self, self.live_trading, exit_reason))
            return
        
        trade_type = self.evaluator.evaluate_entry_conditions()
        if trade_type:
            # TP, SL, risk_per_shareを計算してevaluatorのインスタンス変数に格納
            exit_conditions = self.strategy_params['exit_conditions']
            sl_cond = exit_conditions['stop_loss']
            atr_key = self.evaluator._get_atr_key_for_exit('stop_loss')
            atr_indicator = self.indicators.get(atr_key)
            
            if not atr_indicator or len(atr_indicator) == 0:
                self.logger.debug(f"ATRインジケーター '{atr_key}' が未計算のためスキップします。")
                return
            
            atr_val = atr_indicator[0]
            if not atr_val or atr_val <= 1e-9:
                self.logger.debug(f"ATR値が0のためスキップします。")
                return
            
            self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
            
            self.entry_order = self.executor.place_entry_order(self, trade_type, self.evaluator.entry_reason, self.risk_per_share)
            
    def _log_debug_info(self):
        log_msg = f"\\n===== Bar Check on {self.data.datetime.datetime(0).isoformat()} =====\\n"
        log_msg += "--- Price Data ---\\n"
        for tf_name, data_feed in self.data_feeds.items():
            if len(data_feed) > 0 and data_feed.close[0] is not None:
                dt = data_feed.datetime.datetime(0)
                log_msg += (f"  [{tf_name.upper():<6}] {dt.isoformat()} | "
                            f"O:{data_feed.open[0]:.2f} H:{data_feed.high[0]:.2f} "
                            f"L:{data_feed.low[0]:.2f} C:{data_feed.close[0]:.2f} "
                            f"V:{data_feed.volume[0]:.0f}\\n")
            else:
                log_msg += f"  [{tf_name.upper():<6}] No data available for this bar\\n"
        log_msg += "--- Indicator Values ---\\n"
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
                    log_msg += f"  [{key}]: {', '.join(values)}\\n"
                else:
                    log_msg += f"  [{key}]: Value not ready\\n"
            else:
                log_msg += f"  [{key}]: Not calculated yet\\n"
        self.logger.debug(log_msg)
        
    def log(self, txt, dt=None, level=logging.INFO):
        log_time = dt or self.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')
        if level >= logging.CRITICAL:
            subject = f"【リアルタイム取引】システム警告 ({self.data0._name})"
            self.notif_manager._send_notification(subject, txt, immediate=False)
"""
}

def create_files(files_dict):
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        content = content.strip()
        if content:
            try:
                with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                print(f"  - ファイル作成: {filename}")
            except IOError as e:
                print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- 1. strategy.pyのリファクタリングを開始します ---")
    create_files(project_files)
    print("strategy.pyのリファクタリングが完了しました。")