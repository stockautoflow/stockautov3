import os
import sys
import copy
import logging

# ==============================================================================
# ファイル: create_tmp.py
# 説明: 推奨される修正（根本解決）を適用するパッチファイルです。
#       責務を明確にするため src/core/strategy.py と src/core/trade_evaluator.py
#       を修正済みの内容で上書きします。
# 実行方法: python create_tmp.py
# ==============================================================================

project_files = {
    "src/core/strategy.py": """import backtrader as bt
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
        # --- ロガーと基本プロパティの初期化 ---
        symbol_str = self.data0._name.split('_')[0]
        self.logger = logging.getLogger(f"{self.__class__.__name__}-{symbol_str}")
        
        self.live_trading = self.p.live_trading
        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}

        # --- 戦略パラメータの初期化 ---
        initializer = strategy_initializer.StrategyInitializer('config/strategy_catalog.yml', 'config/strategy_base.yml')
        self.strategy_params = copy.deepcopy(initializer.base_strategy_params)

        if self.p.strategy_assignments:
            strategy_name = self.p.strategy_assignments.get(str(symbol_str))
            if strategy_name:
                catalog = self.p.strategy_catalog if self.p.strategy_catalog is not None else initializer.strategy_catalog
                entry_strategy_def = next((item for item in catalog if item.get("name") == strategy_name), None)
                
                if entry_strategy_def:
                    self.strategy_params.update(entry_strategy_def)
                    self.logger.info(f"銘柄 {symbol_str}: 戦略 '{strategy_name}' を適用します。")
                else:
                    self.logger.warning(f"戦略カタログに '{strategy_name}' が見つかりません。ベース戦略を使用します。")
            else:
                self.logger.warning(f"銘柄 {symbol_str} に戦略が割り当てられていません。ベース戦略を使用します。")
        else:
             self.logger.info(f"個別バックテストモード: ベース戦略 '{self.strategy_params.get('strategy_name')}' を使用します。")

        # --- 依存コンポーネントの初期化 ---
        self.indicators = self._create_indicators(self.strategy_params)
        self.evaluator = trade_evaluator.TradeEvaluator(self.strategy_params, self.data_feeds, self.indicators)
        self.executor = order_executor.OrderExecutor(self.strategy_params, self.data_feeds, self.indicators)
        self.pos_manager = position_manager.PositionManager(self.strategy_params, self.data_feeds, self.indicators)
        self.notif_manager = notification_manager.NotificationManager(self.live_trading, notifier)
        
        # --- 状態変数の初期化 ---
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

    def _create_indicators(self, strategy_params):
        indicators, unique_defs = {}, {}
        
        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            key = self._get_indicator_key(timeframe, **ind_def)
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
        
        backtrader_indicators = {
            'ema': bt.indicators.EMA, 'rsi': bt.indicators.RSI_Safe, 'atr': bt.indicators.ATR,
            'macd': bt.indicators.MACD, 'bollingerbands': bt.indicators.BollingerBands,
            'sma': bt.indicators.SMA, 'stochastic': SafeStochastic, 'vwap': VWAP, 'adx': SafeADX
        }
        
        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'].lower(), ind_def.get('params', {})
            ind_cls = backtrader_indicators.get(name)
            
            if ind_cls:
                try:
                    indicators[key] = ind_cls(self.data_feeds[timeframe], plot=False, **params)
                except Exception as e:
                    self.logger.error(f"インジケーター '{name}' の生成に失敗しました: {e}")
            else:
                self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        if isinstance(strategy_params.get('entry_conditions'), dict):
            for cond_list in strategy_params.get('entry_conditions', {}).values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict) or cond.get('type') not in ['crossover', 'crossunder']: continue
                    ind1_key = self._get_indicator_key(cond['timeframe'], **cond['indicator1'])
                    ind2_key = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    cross_key = f"cross_{ind1_key}_vs_{ind2_key}"
                    if ind1_key in indicators and ind2_key in indicators and cross_key not in indicators:
                        indicators[cross_key] = bt.indicators.CrossOver(indicators[ind1_key], indicators[ind2_key], plot=False)
        return indicators

    def _get_indicator_key(self, timeframe, **ind_def):
        name = ind_def.get('name')
        params = ind_def.get('params', {})
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']:
            return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), name='atr', params=atr_params)

    def start(self):
        self.live_trading_started = True

    def notify_order(self, order):
        # 注文の状態に応じてis_entry, is_exitをinfoから取得
        is_entry = order.info.get('is_entry', False)
        is_exit = order.info.get('is_exit', False)

        self.notif_manager.handle_order_notification(order, self.data0)
        
        if order.status == order.Completed:
            if is_entry:
                if not self.live_trading:
                    exit_orders = self.executor.place_exit_orders(self, self.live_trading, "Backtest")
                    for o in exit_orders:
                        o.info.is_exit = True
                    self.exit_orders = exit_orders
                self.executed_size = order.executed.size
                self.entry_reason_for_trade = self.entry_reason
            
            if is_exit:
                self.sl_price, self.tp_price = 0.0, 0.0

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
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
            atr_key = self._get_atr_key_for_exit('stop_loss')
            if atr_key and self.indicators.get(atr_key) and len(self.indicators.get(atr_key)) > 0:
                self.pos_manager.restore_state(self, self.p.persisted_position)
                self.is_restoring = False
            else:
                self.logger.debug("ポジション復元待機中: インジケーターが未計算です...")
                return

        if self.entry_order or (self.live_trading and self.exit_orders):
            return

        pos_size = self.getposition().size
        if pos_size:
            if self.live_trading:
                exit_reason = self.evaluator.evaluate_exit_conditions(self, self.data.close[0], pos_size > 0)
                if exit_reason:
                    exit_order = self.executor.place_exit_orders(self, self.live_trading, exit_reason)
                    exit_order.info.is_exit = True
                    self.exit_orders.append(exit_order)
            return
        
        trade_type, entry_reason = self.evaluator.evaluate_entry_conditions()
        if not trade_type:
            return

        atr_key = self._get_atr_key_for_exit('stop_loss')
        atr_indicator = self.indicators.get(atr_key)
        
        if not atr_indicator or len(atr_indicator) == 0:
            self.logger.debug(f"ATRインジケーター '{atr_key}' が未計算のためスキップします。")
            return
        
        atr_val = atr_indicator[0]
        if not atr_val or atr_val <= 1e-9:
            self.logger.debug(f"ATR値が0のためスキップします。")
            return
        
        sl_cond = self.strategy_params['exit_conditions']['stop_loss']
        self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
        
        self.entry_order = self.executor.place_entry_order(self, trade_type, entry_reason, self.risk_per_share)
        if self.entry_order:
            self.entry_order.info.is_entry = True

    def _log_debug_info(self):
        # (このメソッドは変更なし)
        pass
        
    def log(self, txt, dt=None, level=logging.INFO):
        # (このメソッドは変更なし)
        pass
""",
    "src/core/trade_evaluator.py": """import logging

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

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or \
                     (cross_indicator[0] < 0 and cond_type == 'crossunder')

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
""",
}

def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        content = content.strip()
        
        if content:
            try:
                with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                print(f"✅ ファイルを修正/作成しました: {filename}")
            except IOError as e:
                print(f"❌ エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- ⚙️ 推奨される修正内容（根本解決）を適用します ---")
    create_files(project_files)
    print("\\n--- ✅ パッチの適用が完了しました ---")