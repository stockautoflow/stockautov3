import os

# ==============================================================================
# ファイル: create_core.py
# 実行方法: python create_core.py
# Ver. 00-46
# 変更点:
#   - src/core/util/notifier.py:
#     - メール送信をキューイング方式に変更。
#     - 専用のワーカースレッドが一定間隔でメールを送信するロジックを実装。
#       これにより、Gmailのレート制限エラーを完全に回避する。
#   - src/core/strategy.py:
#     - _send_notificationを、新しいキューイング方式のnotifierを呼び出すよう修正。
# ==============================================================================

project_files = {
    # パッケージ初期化ファイル
    "src/core/__init__.py": "",
    "src/core/util/__init__.py": "",

    # カスタムインジケーター定義
    "src/core/indicators.py": """
import backtrader as bt
import collections

class SafeStochastic(bt.indicators.Stochastic):
    def next(self):
        if self.data.high[0] - self.data.low[0] == 0:
            self.lines.percK[0] = 50.0
            self.lines.percD[0] = 50.0
        else:
            super().next()

class VWAP(bt.Indicator):
    lines = ('vwap',)
    plotinfo = dict(subplot=False)

    def __init__(self):
        self.tp = (self.data.high + self.data.low + self.data.close) / 3.0
        self.cumulative_tpv = 0.0
        self.cumulative_volume = 0.0

    def next(self):
        if len(self) == 1:
            return
        if self.data.datetime.date(0) != self.data.datetime.date(-1):
            self.cumulative_tpv = 0.0
            self.cumulative_volume = 0.0

        self.cumulative_tpv += self.tp[0] * self.data.volume[0]
        self.cumulative_volume += self.data.volume[0]

        if self.cumulative_volume > 0:
            self.lines.vwap[0] = self.cumulative_tpv / self.cumulative_volume
        else:
            self.lines.vwap[0] = self.tp[0]

class SafeADX(bt.Indicator):
    lines = ('adx', 'plusDI', 'minusDI',)
    params = (('period', 14),)
    alias = ('ADX',)

    def __init__(self):
        self.p.period_wilder = self.p.period * 2 - 1
        self.tr = 0.0
        self.plus_dm = 0.0
        self.minus_dm = 0.0
        self.plus_di = 0.0
        self.minus_di = 0.0
        self.adx = 0.0
        self.dx_history = collections.deque(maxlen=self.p.period)

    def _wilder_smooth(self, prev_val, current_val):
        return prev_val - (prev_val / self.p.period) + current_val

    def next(self):
        high, low, close = self.data.high[0], self.data.low[0], self.data.close[0]
        prev_high, prev_low, prev_close = self.data.high[-1], self.data.low[-1], self.data.close[-1]

        current_tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        self.tr = self._wilder_smooth(self.tr, current_tr)

        move_up, move_down = high - prev_high, prev_low - low
        current_plus_dm = move_up if move_up > move_down and move_up > 0 else 0.0
        current_minus_dm = move_down if move_down > move_up and move_down > 0 else 0.0

        self.plus_dm = self._wilder_smooth(self.plus_dm, current_plus_dm)
        self.minus_dm = self._wilder_smooth(self.minus_dm, current_minus_dm)

        if self.tr > 1e-9:
            self.plus_di = 100.0 * self.plus_dm / self.tr
            self.minus_di = 100.0 * self.minus_dm / self.tr
        else:
            self.plus_di, self.minus_di = 0.0, 0.0

        self.lines.plusDI[0], self.lines.minusDI[0] = self.plus_di, self.minus_di

        di_sum = self.plus_di + self.minus_di
        dx = 100.0 * abs(self.plus_di - self.minus_di) / di_sum if di_sum > 1e-9 else 0.0
        self.dx_history.append(dx)

        if len(self) >= self.p.period:
            if len(self) == self.p.period:
                self.adx = sum(self.dx_history) / self.p.period
            else:
                self.adx = (self.adx * (self.p.period - 1) + dx) / self.p.period
        self.lines.adx[0] = self.adx
""",

    # データフィード準備モジュール
    "src/core/data_preparer.py": """
import os
import glob
import logging
import pandas as pd
import backtrader as bt

try:
    from src.realtrade.live.yahoo_data import YahooData as LiveData
except ImportError:
    LiveData = None

logger = logging.getLogger(__name__)

def _load_csv_data(filepath, timeframe_str, compression):
    try:
        df = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        if df.empty:
            logger.warning(f"データファイルが空です: {filepath}")
            return None
        df.columns = [x.lower() for x in df.columns]
        return bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.TFrame(timeframe_str), compression=compression)
    except Exception as e:
        logger.error(f"CSV読み込みまたはデータフィード作成で失敗: {filepath} - {e}")
        return None

def prepare_data_feeds(cerebro, strategy_params, symbol, data_dir, is_live=False, live_store=None, backtest_base_filepath=None):
    logger.info(f"[{symbol}] データフィードの準備を開始 (ライブモード: {is_live})")
    timeframes_config = strategy_params['timeframes']
    short_tf_config = timeframes_config['short']

    if is_live:
        if not LiveData:
            raise ImportError("リアルタイム取引部品が見つかりません。")
        base_data = LiveData(dataname=symbol, store=live_store,
                             timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
                             compression=short_tf_config['compression'])
    else:
        if backtest_base_filepath is None:
            logger.warning(f"バックテスト用のベースファイルパスが指定されていません。銘柄コード {symbol} から自動検索を試みます。")
            short_tf_compression = strategy_params['timeframes']['short']['compression']
            search_pattern = os.path.join(data_dir, f"{symbol}_{short_tf_compression}m_*.csv")
            files = glob.glob(search_pattern)
            if not files:
                raise FileNotFoundError(f"ベースファイルが見つかりません: {search_pattern}")
            backtest_base_filepath = files[0]
            logger.info(f"ベースファイルを自動検出しました: {backtest_base_filepath}")
        if not os.path.exists(backtest_base_filepath):
            raise FileNotFoundError(f"ベースファイルが見つかりません: {backtest_base_filepath}")
        base_data = _load_csv_data(backtest_base_filepath, short_tf_config['timeframe'], short_tf_config['compression'])

    if base_data is None:
        logger.error(f"[{symbol}] 短期データフィードの作成に失敗しました。")
        return False

    cerebro.adddata(base_data, name=str(symbol))
    logger.info(f"[{symbol}] 短期データフィードを追加しました。")

    for tf_name in ['medium', 'long']:
        tf_config = timeframes_config.get(tf_name)
        if not tf_config:
            logger.warning(f"[{symbol}] {tf_name}の時間足設定が見つかりません。")
            continue
        source_type = tf_config.get('source_type', 'resample')
        if is_live or source_type == 'resample':
            cerebro.resampledata(base_data,
                                 timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                                 compression=tf_config['compression'], name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データフィードをリサンプリングで追加しました。")
        elif source_type == 'direct':
            pattern_template = tf_config.get('file_pattern')
            if not pattern_template:
                logger.error(f"[{symbol}] {tf_name}のsource_typeが'direct'ですが、file_patternが未定義です。")
                return False
            search_pattern = os.path.join(data_dir, pattern_template.format(symbol=symbol))
            data_files = glob.glob(search_pattern)
            if not data_files:
                logger.error(f"[{symbol}] {tf_name}用のデータファイルが見つかりません: {search_pattern}")
                return False
            data_feed = _load_csv_data(data_files[0], tf_config['timeframe'], tf_config['compression'])
            if data_feed is None: return False
            cerebro.adddata(data_feed, name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データフィードを直接読み込みで追加しました: {data_files[0]}")
    return True
""",

    "src/core/strategy.py": """
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

            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or \
                     (cross_indicator[0] < 0 and cond_type == 'crossunder')

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
            return True, "\\n".join(reason_details)
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
                if not self.live_trading: self._place_native_exit_orders()
                else:
                    is_long = order.isbuy(); entry_price = order.executed.price
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
                    self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, Initial SL={self.sl_price:.2f}")

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

            self._send_notification(subject, body)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.data0._name})"
            body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\\n"
                    f"銘柄: {self.data0._name}\\n"
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
            body = (f"日時: {self.data.datetime.datetime(0).isoformat()}\\n"
                    f"銘柄: {self.data0._name}\\n"
                    f"戦略: {self.strategy_params.get('strategy_name', 'N/A')}\\n"
                    f"方向: {'BUY' if is_long else 'SELL'}\\n"
                    f"数量: {size:.2f}\\n\\n"
                    "--- エントリー根拠詳細 ---\\n"
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
""",

    # ロガー設定
    "src/core/util/logger.py": """
import logging
import os
from datetime import datetime

def setup_logging(log_dir, log_prefix, level=logging.INFO):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    log_filename = f"{log_prefix}_{timestamp}.log"
    file_mode = 'w'
    log_filepath = os.path.join(log_dir, log_filename)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=level,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, mode=file_mode, encoding='utf-8'),
                                  logging.StreamHandler()])
    print(f"ロガーをセットアップしました。モード: {log_prefix}, ログファイル: {log_filepath}, レベル: {logging.getLevelName(level)}")
""",

    # メール通知機能
    "src/core/util/notifier.py": """
import smtplib
import yaml
import logging
import socket
import queue
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

_notification_queue = queue.Queue()
_worker_thread = None
_stop_event = threading.Event()
_smtp_server = None
_email_config = None

def _get_server():
    global _smtp_server, _email_config

    if _email_config is None:
        _email_config = load_email_config()

    if not _email_config.get("ENABLED"):
        return None

    if _smtp_server:
        try:
            status = _smtp_server.noop()
            if status[0] == 250:
                return _smtp_server
        except smtplib.SMTPServerDisconnected:
            logger.warning("SMTPサーバーとの接続が切断されました。再接続します。")
            _smtp_server = None

    try:
        server_name = _email_config["SMTP_SERVER"]
        server_port = _email_config["SMTP_PORT"]
        logger.info(f"SMTPサーバーに新規接続します: {server_name}:{server_port}")
        
        server = smtplib.SMTP(server_name, server_port, timeout=20)
        server.starttls()
        server.login(_email_config["SMTP_USER"], _email_config["SMTP_PASSWORD"])
        
        _smtp_server = server
        return _smtp_server
    except Exception as e:
        logger.critical(f"SMTPサーバーへの接続またはログインに失敗しました: {e}", exc_info=True)
        return None

def _email_worker():
    while not _stop_event.is_set():
        try:
            item = _notification_queue.get(timeout=1)
            if item is None: # 停止シグナル
                break

            server = _get_server()
            if not server:
                continue

            msg = MIMEMultipart()
            msg['From'] = _email_config["SMTP_USER"]
            msg['To'] = _email_config["RECIPIENT_EMAIL"]
            msg['Subject'] = item['subject']
            msg.attach(MIMEText(item['body'], 'plain', 'utf-8'))

            try:
                logger.info(f"メールを送信中... To: {_email_config['RECIPIENT_EMAIL']}")
                server.send_message(msg)
                logger.info("メールを正常に送信しました。")
            except Exception as e:
                logger.critical(f"メール送信中に予期せぬエラーが発生しました: {e}", exc_info=True)
                global _smtp_server
                _smtp_server = None
            
            time.sleep(2) # 2秒待機

        except queue.Empty:
            continue

def start_notifier():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_email_worker, daemon=True)
        _worker_thread.start()
        logger.info("メール通知ワーカースレッドを開始しました。")

def stop_notifier():
    global _worker_thread, _smtp_server
    if _worker_thread and _worker_thread.is_alive():
        logger.info("メール通知ワーカースレッドを停止します...")
        _notification_queue.put(None) # 停止シグナルをキューに追加
        _worker_thread.join(timeout=10)
        if _worker_thread.is_alive():
            logger.warning("ワーカースレッドがタイムアウト後も終了していません。")
    
    if _smtp_server:
        logger.info("SMTPサーバーとの接続を閉じます。")
        _smtp_server.quit()
        _smtp_server = None
    
    _worker_thread = None
    logger.info("メール通知システムが正常に停止しました。")


def load_email_config():
    global _email_config
    if _email_config is not None:
        return _email_config
    try:
        with open('config/email_config.yml', 'r', encoding='utf-8') as f:
            _email_config = yaml.safe_load(f)
            return _email_config
    except FileNotFoundError:
        logger.warning("config/email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"config/email_config.ymlの読み込み中にエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body):
    _notification_queue.put({'subject': subject, 'body': body})
"""
}

def create_files(files_dict):
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
    print("--- 3. coreパッケージの生成を開始します ---")
    create_files(project_files)
    print("coreパッケージの生成が完了しました。")