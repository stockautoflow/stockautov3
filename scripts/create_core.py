import os

# ==============================================================================
# ファイル: create_core.py
# 実行方法: python create_core.py
# Ver. 00-26
# 変更点:
#   - src/core/util/logger.py (setup_logging):
#     - ログレベルを設定するための 'level' 引数を追加。
#       これにより、各実行モジュール（realtrade, backtest等）の
#       設定ファイルから渡されたログレベルが正しく反映されるようになります。
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
        # 高値と安値が同じ場合に発生するゼロ除算を回避
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
        # 日付が変わったらリセット
        if self.data.datetime.date(0) != self.data.datetime.date(-1):
            self.cumulative_tpv = 0.0
            self.cumulative_volume = 0.0
        
        self.cumulative_tpv += self.tp[0] * self.data.volume[0]
        self.cumulative_volume += self.data.volume[0]
        
        # 出来高が0の場合のゼロ除算を回避
        if self.cumulative_volume > 0:
            self.lines.vwap[0] = self.cumulative_tpv / self.cumulative_volume
        else:
            self.lines.vwap[0] = self.tp[0]

class SafeADX(bt.Indicator):
    \"\"\"
    【最終版】標準ADXの計算ロジックを完全に内包し、外部依存をなくした
    「完全自己完結型」のADXインジケーター。
    これにより、計算の正確性とシステムの堅牢性を完全に両立させる。
    \"\"\"
    lines = ('adx', 'plusDI', 'minusDI',)
    params = (('period', 14),)
    alias = ('ADX',)

    def __init__(self):
        self.p.period_wilder = self.p.period * 2 - 1
        
        # 内部計算用の変数を初期化
        self.tr = 0.0
        self.plus_dm = 0.0
        self.minus_dm = 0.0
        self.plus_di = 0.0
        self.minus_di = 0.0
        self.adx = 0.0
        
        # DXの履歴を保持するためのdeque
        self.dx_history = collections.deque(maxlen=self.p.period)

    def _wilder_smooth(self, prev_val, current_val):
        return prev_val - (prev_val / self.p.period) + current_val

    def next(self):
        high = self.data.high[0]
        low = self.data.low[0]
        close = self.data.close[0]
        prev_high = self.data.high[-1]
        prev_low = self.data.low[-1]
        prev_close = self.data.close[-1]

        # --- True Rangeの計算 ---
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        current_tr = max(tr1, tr2, tr3)
        self.tr = self._wilder_smooth(self.tr, current_tr)

        # --- +DM, -DMの計算 ---
        move_up = high - prev_high
        move_down = prev_low - low
        
        current_plus_dm = 0.0
        if move_up > move_down and move_up > 0:
            current_plus_dm = move_up
        
        current_minus_dm = 0.0
        if move_down > move_up and move_down > 0:
            current_minus_dm = move_down
            
        self.plus_dm = self._wilder_smooth(self.plus_dm, current_plus_dm)
        self.minus_dm = self._wilder_smooth(self.minus_dm, current_minus_dm)

        # --- +DI, -DIの計算 (ゼロ除算回避) ---
        if self.tr > 1e-9:
            self.plus_di = 100.0 * self.plus_dm / self.tr
            self.minus_di = 100.0 * self.minus_dm / self.tr
        else:
            self.plus_di = 0.0
            self.minus_di = 0.0
            
        self.lines.plusDI[0] = self.plus_di
        self.lines.minusDI[0] = self.minus_di

        # --- DX, ADXの計算 (ゼロ除算回避) ---
        di_sum = self.plus_di + self.minus_di
        dx = 0.0
        if di_sum > 1e-9:
            dx = 100.0 * abs(self.plus_di - self.minus_di) / di_sum
        
        self.dx_history.append(dx)
        
        if len(self.dx_history) == self.p.period:
            if len(self) == self.p.period: # 最初のADX計算
                self.adx = sum(self.dx_history) / self.p.period
            else: # 2回目以降のADX計算
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

# リアルタイム取引用のクラスを動的にインポート
try:
    from src.realtrade.live.yahoo_data import YahooData as LiveData
except ImportError:
    LiveData = None # リアルタイム部品が存在しない場合のエラー回避

logger = logging.getLogger(__name__)

def _load_csv_data(filepath, timeframe_str, compression):
    \"\"\"単一のCSVファイルを読み込み、PandasDataフィードを返す\"\"\"
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
    \"\"\"
    Cerebroに3つの時間足のデータフィード（短期・中期・長期）をセットアップする共通関数。
    \"\"\"
    logger.info(f"[{symbol}] データフィードの準備を開始 (ライブモード: {is_live})")
    
    timeframes_config = strategy_params['timeframes']
    
    # 1. 短期データフィードの準備
    short_tf_config = timeframes_config['short']
    if is_live:
        if not LiveData:
            raise ImportError("リアルタイム取引部品が見つかりません。'create_realtrade.py'を実行してください。")
        base_data = LiveData(dataname=symbol, store=live_store, 
                             timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']), 
                             compression=short_tf_config['compression'])
    else:
        # [修正] バックテスト/シミュレーションモードの場合
        # ファイルパスが指定されていない場合、銘柄コードから自動で検索する
        if backtest_base_filepath is None:
            logger.warning(f"バックテスト用のベースファイルパスが指定されていません。銘柄コード {symbol} から自動検索を試みます。")
            short_tf_compression = strategy_params['timeframes']['short']['compression']
            search_pattern = os.path.join(data_dir, f"{symbol}_{short_tf_compression}m_*.csv")
            files = glob.glob(search_pattern)
            if not files:
                raise FileNotFoundError(f"バックテスト/シミュレーション用のベースファイルが見つかりません。検索パターン: {search_pattern}")
            backtest_base_filepath = files[0] # 最初に見つかったファイルを使用
            logger.info(f"ベースファイルを自動検出しました: {backtest_base_filepath}")

        if not os.path.exists(backtest_base_filepath):
            raise FileNotFoundError(f"指定されたバックテスト用のベースファイルが見つかりません: {backtest_base_filepath}")
        
        base_data = _load_csv_data(backtest_base_filepath, short_tf_config['timeframe'], short_tf_config['compression'])

    if base_data is None:
        logger.error(f"[{symbol}] 短期データフィードの作成に失敗しました。処理を中断します。")
        return False
        
    cerebro.adddata(base_data, name=str(symbol))
    logger.info(f"[{symbol}] 短期データフィードを追加しました。")

    # 2. 中期・長期データフィードの準備
    for tf_name in ['medium', 'long']:
        tf_config = timeframes_config.get(tf_name)
        if not tf_config:
            logger.warning(f"[{symbol}] {tf_name}の時間足設定が見つかりません。スキップします。")
            continue

        source_type = tf_config.get('source_type', 'resample')
        
        if is_live or source_type == 'resample':
            cerebro.resampledata(base_data, 
                                 timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']), 
                                 compression=tf_config['compression'],
                                 name=tf_name)
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
            if data_feed is None:
                return False
            
            cerebro.adddata(data_feed, name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データフィードを直接読み込みで追加しました: {data_files[0]}")

    return True
""",

    # 戦略ロジック本体
    "src/core/strategy.py": """
import backtrader as bt
import logging
import inspect
import yaml
import copy
from .indicators import SafeStochastic, VWAP, SafeADX

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
            elif name.lower() == 'adx': ind_cls = SafeADX
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
        if not atr_val or atr_val <= 1e-9: return
        self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
        
        if self.risk_per_share < 1e-9:
             self.log(f"計算されたリスクが0のため、エントリーをスキップします。ATR: {atr_val}")
             return

        entry_price = self.data_feeds['short'].close[0]
        sizing = self.strategy_params.get('sizing', {})
        size = min((self.broker.getcash()*sizing.get('risk_per_trade',0.01))/self.risk_per_share,
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
                    if not tp_atr_val or tp_atr_val <= 1e-9:
                         self.tp_price = 0
                    else:
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
        if self.entry_order:
            return
        if self.live_trading and self.exit_orders:
            return
        if self.getposition().size:
            if self.live_trading:
                self._check_live_exit_conditions()
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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

def load_email_config():
    try:
        with open('config/email_config.yml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("config/email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"config/email_config.ymlの読み込み中にエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body):
    email_config = load_email_config()
    if not email_config.get("ENABLED"):
        return
    msg = MIMEMultipart()
    msg['From'] = email_config["SMTP_USER"]
    msg['To'] = email_config["RECIPIENT_EMAIL"]
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    try:
        logger.info(f"メールを送信中... To: {email_config['RECIPIENT_EMAIL']}")
        server = smtplib.SMTP(email_config["SMTP_SERVER"], email_config["SMTP_PORT"])
        server.starttls()
        server.login(email_config["SMTP_USER"], email_config["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        logger.info("メールを正常に送信しました。")
    except Exception as e:
        logger.error(f"メール送信中にエラーが発生しました: {e}")
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
