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