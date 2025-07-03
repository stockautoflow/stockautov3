# ==============================================================================
# ファイル: create_project_files_realtime.py
# 説明: このスクリプトは、リアルタイム自動トレードシステムに
#       必要なファイルとディレクトリの骨格を生成します。
# バージョン: v18.9
# 主な変更点:
#   - 状態復元後のDB更新バグを修正
#   - analyzer.py:
#     - ポジション決済時の通知処理を修正。`trade.isclosed`を正しく判定し、
#       DBからポジションを削除するように変更。
#     - `trade.isopen`が通知された際に、ポジションサイズが0の場合は無視する
#       ロジックを追加し、堅牢性を向上。
# ==============================================================================
import os

# btrader_strategy.py の新しい内容
btrader_strategy_content = """import backtrader as bt
import logging
import inspect
import yaml

# === カスタムインジケーター定義 ===
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
        if len(self) == 1: return
        if self.data.datetime.date(0) != self.data.datetime.date(-1):
            self.cumulative_tpv = 0.0
            self.cumulative_volume = 0.0
        self.cumulative_tpv += self.tp[0] * self.data.volume[0]
        self.cumulative_volume += self.data.volume[0]
        if self.cumulative_volume > 0:
            self.lines.vwap[0] = self.cumulative_tpv / self.cumulative_volume
        else:
            self.lines.vwap[0] = self.tp[0]

# === メイン戦略クラス ===
class DynamicStrategy(bt.Strategy):
    params = (
        ('strategy_params', None),
        ('strategy_catalog', None),
        ('strategy_assignments', None),
        ('live_trading', False),
    )

    def __init__(self):
        self.live_trading = self.p.live_trading
        
        if self.p.strategy_catalog and self.p.strategy_assignments:
            symbol_str = self.data._name
            symbol = int(symbol_str) if symbol_str.isdigit() else symbol_str
            strategy_name = self.p.strategy_assignments.get(str(symbol))
            if not strategy_name: raise ValueError(f"銘柄 {symbol} に戦略が割り当てられていません。")
            
            try:
                with open('strategy.yml', 'r', encoding='utf-8') as f: base_strategy = yaml.safe_load(f)
            except FileNotFoundError: raise FileNotFoundError("共通基盤ファイル 'strategy.yml' が見つかりません。")

            entry_strategy_def = self.p.strategy_catalog.get(strategy_name)
            if not entry_strategy_def: raise ValueError(f"エントリー戦略カタログ 'strategies.yml' に '{strategy_name}' が見つかりません。")
            
            import copy
            self.strategy_params = copy.deepcopy(base_strategy)
            self.strategy_params.update(entry_strategy_def)
            self.logger = logging.getLogger(f"{self.__class__.__name__}-{symbol}")

        elif self.p.strategy_params:
            self.strategy_params = self.p.strategy_params
            self.logger = logging.getLogger(self.__class__.__name__)
        else:
            raise ValueError("戦略パラメータが見つかりません。")

        if not isinstance(self.strategy_params.get('exit_conditions'), dict): raise ValueError(f"戦略 '{self.strategy_params.get('name')}' に exit_conditions が定義されていません。")
        if not isinstance(self.strategy_params.get('exit_conditions', {}).get('stop_loss'), dict): raise ValueError(f"戦略 '{self.strategy_params.get('name')}' の exit_conditions に stop_loss が定義されていません。")

        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()
        
        self.entry_order, self.exit_orders = None, []
        self.entry_reason, self.entry_reason_for_trade, self.executed_size = "", "", 0
        self.risk_per_share, self.tp_price, self.sl_price = 0.0, 0.0, 0.0
        self.current_position_entry_dt = None
        self.restored_position_setup_needed = False

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
                else: self._setup_live_exit_prices(order.executed.price, order.isbuy())
            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log(f"エントリー注文失敗/キャンセル: {order.getstatusname()}")
                self.sl_price, self.tp_price, self.risk_per_share = 0.0, 0.0, 0.0
            self.entry_order = None

        elif self.exit_orders and any(o.ref == order.ref for o in self.exit_orders if o):
            if order.status == order.Completed:
                self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
                self.sl_price, self.tp_price, self.risk_per_share = 0.0, 0.0, 0.0
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

    def start(self):
        position = self.getposition()
        if position.size != 0:
            self.log(f"状態復元: 既存ポジションを検出。 Size: {position.size}, Price: {position.price}。決済価格はnext()でセットアップします。")
            self.restored_position_setup_needed = True
        else:
            self.log("状態復元: 既存ポジションは検出されませんでした。")

    def _setup_live_exit_prices(self, entry_price, is_long):
        exit_conditions = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conditions.get('stop_loss', {})
        tp_cond = exit_conditions.get('take_profit', {})
        
        # ATRインジケーターが準備できているか確認
        sl_atr_key = self._get_indicator_key(sl_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in sl_cond.get('params', {}).items() if k!='multiplier'})
        if not self.indicators.get(sl_atr_key) or len(self.indicators[sl_atr_key]) == 0:
            self.log("決済価格設定不可: 損切り用ATRが未準備です。")
            return

        atr_val = self.indicators[sl_atr_key][0]
        self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
        self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share

        if tp_cond:
            tp_atr_key = self._get_indicator_key(tp_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in tp_cond.get('params', {}).items() if k!='multiplier'})
            if self.indicators.get(tp_atr_key) and len(self.indicators[tp_atr_key]) > 0:
                tp_atr_val = self.indicators[tp_atr_key][0]
                tp_multiplier = tp_cond.get('params', {}).get('multiplier', 5.0)
                self.tp_price = entry_price + tp_atr_val * tp_multiplier if is_long else entry_price - tp_atr_val * tp_multiplier
            else:
                self.log("利確価格設定不可: 利確用ATRが未準備です。")
                self.tp_price = 0.0
        
        self.log(f"ライブモード決済価格設定完了: TP={self.tp_price:.2f}, SL={self.sl_price:.2f}, Risk/Share={self.risk_per_share:.2f}")

    def _place_native_exit_orders(self):
        if not self.getposition().size: return
        is_long, size = self.getposition().size > 0, abs(self.getposition().size)
        
        # エントリー時に計算した決済価格を使用
        limit_order = None
        if self.tp_price != 0:
            limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False)
            self.log(f"利確(Limit)注文を作成: Price={self.tp_price:.2f}")
        
        if self.risk_per_share > 0:
            stop_order = self.sell(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order) if is_long else self.buy(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order)
            self.log(f"損切(StopTrail)注文をOCOで発注: TrailAmount={self.risk_per_share:.2f}")
            self.exit_orders = [limit_order, stop_order] if limit_order else [stop_order]

    def _check_live_exit_conditions(self):
        pos, current_price, is_long = self.getposition(), self.data.close[0], self.getposition().size > 0
        
        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            self.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
            self.exit_orders.append(self.close())
            return

        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                self.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                self.exit_orders.append(self.close())
                return
            new_sl_price = (current_price - self.risk_per_share) if is_long else (current_price + self.risk_per_share)
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                self.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                self.sl_price = new_sl_price

    def _check_entry_conditions(self):
        entry_price = self.data_feeds['short'].close[0]
        self._setup_live_exit_prices(entry_price, is_long=True) # 仮でis_long=Trueとして計算
        if self.risk_per_share <= 0: return

        sizing = self.strategy_params.get('sizing', {})
        size = min((self.broker.getcash()*sizing.get('risk_per_trade',0.01))/self.risk_per_share,
                   sizing.get('max_investment_per_trade', 10000000)/entry_price)
        if size <= 0: return

        def place_order(trade_type, reason):
            self.entry_reason, is_long = reason, trade_type == 'long'
            self._setup_live_exit_prices(entry_price, is_long) # 正しい方向で再計算
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
        if self.restored_position_setup_needed:
            position = self.getposition()
            self.log(f"next()にて復元ポジションの決済価格をセットアップします。")
            self._setup_live_exit_prices(entry_price=position.price, is_long=(position.size > 0))
            self.restored_position_setup_needed = False

        if self.entry_order: return
        if self.live_trading and self.exit_orders: return
        if self.getposition().size:
            if self.live_trading: self._check_live_exit_conditions()
            return
        self._check_entry_conditions()

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
"""

project_files = {
    "requirements_realtime.txt": """backtrader
pandas
numpy
PyYAML
python-dotenv
yfinance
""",

    ".env.example": """# このファイルをコピーして .env という名前のファイルを作成し、
# 実際のAPIキーに書き換えてください。
# .env ファイルは .gitignore に追加し、バージョン管理に含めないでください。

# --- 証券会社API (DATA_SOURCE='SBI'の場合に必要) ---
API_KEY="YOUR_API_KEY_HERE"
API_SECRET="YOUR_API_SECRET_HERE"
""",

    "config_realtrade.py": """import os
import logging

# ==============================================================================
# --- グローバル設定 ---
# ==============================================================================
# Trueにすると実際の証券会社APIやデータソースに接続します。
# FalseにするとMockDataFetcherを使用し、シミュレーションを実行します。
LIVE_TRADING = True

# ライブトレーディング時のデータソースを選択: 'SBI' または 'YAHOO'
# 'YAHOO' を選択した場合、売買機能はシミュレーション(BackBroker)になります。
DATA_SOURCE = 'YAHOO'

# [追加] YAHOOモード/シミュレーションモードでの初期資金
INITIAL_CASH = 10000000

# --- API認証情報 (環境変数からロード) ---
# DATA_SOURCEが'SBI'の場合に利用されます
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

if LIVE_TRADING:
    print(f"<<< ライブモード ({DATA_SOURCE}) で起動します >>>")
    if DATA_SOURCE == 'SBI':
        if not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
            raise ValueError("環境変数 'API_KEY' が設定されていません。")
        if not API_SECRET or API_SECRET == "YOUR_API_SECRET_HERE":
            raise ValueError("環境変数 'API_SECRET' が設定されていません。")
else:
    print("<<< シミュレーションモードで起動します (MockDataFetcher使用) >>>")


# ==============================================================================
# --- 取引設定 ---
# ==============================================================================
# 1注文あたりの最大投資額（日本円）
MAX_ORDER_SIZE_JPY = 1000000

# 同時に発注できる最大注文数
MAX_CONCURRENT_ORDERS = 5

# 緊急停止する資産減少率の閾値 (例: -0.1は資産が10%減少したら停止)
EMERGENCY_STOP_THRESHOLD = -0.1

# 取引対象の銘柄と戦略が書かれたファイル名のパターン
RECOMMEND_FILE_PATTERN = "all_recommend_*.csv"


# ==============================================================================
# --- システム設定 ---
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- データベース ---
DB_PATH = os.path.join(BASE_DIR, "realtrade", "db", "realtrade_state.db")

# --- ロギング ---
LOG_LEVEL = logging.INFO
LOG_DIR = os.path.join(BASE_DIR, 'log')

print("設定ファイルをロードしました (config_realtrade.py)")
""",

    "btrader_strategy.py": btrader_strategy_content,

    "run_realtrade.py": """import logging
import time
import yaml
import pandas as pd
import glob
import os
from dotenv import load_dotenv
import backtrader as bt

# 環境変数をロード
load_dotenv()

# モジュールをインポート
import config_realtrade as config
import logger_setup
import btrader_strategy
from realtrade.state_manager import StateManager
from realtrade.analyzer import TradePersistenceAnalyzer

# --- モードに応じてインポートするモジュールを切り替え ---
if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'SBI':
        from realtrade.live.sbi_store import SBIStore as LiveStore
        from realtrade.live.sbi_broker import SBIBroker as LiveBroker
        from realtrade.live.sbi_data import SBIData as LiveData
    elif config.DATA_SOURCE == 'YAHOO':
        from realtrade.live.yahoo_store import YahooStore as LiveStore
        from realtrade.brokers.custom_back_broker import CustomBackBroker as LiveBroker
        from realtrade.live.yahoo_data import YahooData as LiveData
    else:
        raise ValueError(f"サポートされていないDATA_SOURCEです: {config.DATA_SOURCE}")
else:
    from realtrade.mock.data_fetcher import MockDataFetcher

# ロガーのセットアップ
logger_setup.setup_logging(config, log_prefix='realtime')
logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_strategy_catalog('strategies.yml')
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.symbols = [s for s in self.symbols if s and str(s).lower() != 'nan']
        self.state_manager = StateManager(config.DB_PATH)
        self.persisted_positions = self.state_manager.load_positions()
        
        self.cerebro = self._setup_cerebro()
        self.is_running = False

    def _load_strategy_catalog(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return {s['name']: s for s in yaml.safe_load(f)}
        except FileNotFoundError:
            logger.error(f"戦略カタログファイル '{filepath}' が見つかりません。")
            raise

    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files:
            raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"最新の対応ファイルをロード: {latest_file}")
        df = pd.read_csv(latest_file)
        strategy_col, symbol_col = df.columns[0], df.columns[1]
        return pd.Series(df[strategy_col].values, index=df[symbol_col].astype(str)).to_dict()

    def _setup_cerebro(self):
        logger.info("Cerebroエンジンをセットアップ中...")
        cerebro = bt.Cerebro(runonce=False)
        
        if config.LIVE_TRADING:
            logger.info(f"ライブモード({config.DATA_SOURCE})用のStore, Broker, DataFeedをセットアップします。")
            if config.DATA_SOURCE == 'SBI':
                store = LiveStore(api_key=config.API_KEY, api_secret=config.API_SECRET)
                broker = LiveBroker(store=store, persisted_positions=self.persisted_positions)
            else: # YAHOO
                store = LiveStore()
                broker = LiveBroker(cash=config.INITIAL_CASH, persisted_positions=self.persisted_positions) 
            
            cerebro.setbroker(broker)
            logger.info(f"-> {broker.__class__.__name__}をCerebroにセットしました。")
            
            for symbol in self.symbols:
                data_feed = LiveData(dataname=symbol, store=store)
                cerebro.adddata(data_feed, name=str(symbol))
            logger.info(f"-> {len(self.symbols)}銘柄の{LiveData.__name__}フィードをCerebroに追加しました。")
            
        else: # Simulation Mode
            logger.info("シミュレーションモード用のBrokerとDataFeedをセットアップします。")
            data_fetcher = MockDataFetcher(symbols=self.symbols, config=config)
            broker = bt.brokers.BackBroker(cash=config.INITIAL_CASH)
            cerebro.setbroker(broker)
            logger.info("-> 標準のBackBrokerをセットしました。")
            for symbol in self.symbols:
                data_feed = data_fetcher.get_data_feed(str(symbol))
                cerebro.adddata(data_feed, name=str(symbol))
            logger.info(f"-> {len(self.symbols)}銘柄のMockデータフィードをCerebroに追加しました。")
        
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        logger.info("-> 永続化用AnalyzerをCerebroに追加しました。")

        cerebro.addstrategy(btrader_strategy.DynamicStrategy,
                            strategy_catalog=self.strategy_catalog,
                            strategy_assignments=self.strategy_assignments,
                            live_trading=config.LIVE_TRADING)
        logger.info(f"-> DynamicStrategyをCerebroに追加しました (live_trading={config.LIVE_TRADING})。")
        
        logger.info("Cerebroエンジンのセットアップが完了しました。")
        return cerebro

    def start(self):
        logger.info("システムを開始します。")
        self.is_running = True
        self.cerebro.run()
        logger.info("Cerebroの実行が完了しました。")
        self.is_running = False

    def stop(self):
        logger.info("システムを停止します。")
        self.is_running = False
        if self.state_manager:
            self.state_manager.close()
        logger.info("システムが正常に停止しました。")

if __name__ == '__main__':
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
    except KeyboardInterrupt:
        logger.info("\\nCtrl+Cを検知しました。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader:
            trader.stop()
    logger.info("--- リアルタイムトレードシステム終了 ---")
""",

    "realtrade/brokers/__init__.py": """# このファイルは'brokers'ディレクトリをPythonパッケージとして認識させるためのものです。
""",

    "realtrade/brokers/custom_back_broker.py": """import backtrader as bt
import logging
from backtrader.position import Position

logger = logging.getLogger(__name__)

class CustomBackBroker(bt.brokers.BackBroker):
    def __init__(self, persisted_positions=None, **kwargs):
        super(CustomBackBroker, self).__init__(**kwargs)
        self.persisted_positions = persisted_positions or {}
        logger.info(f"CustomBackBrokerを初期化しました。Initial Cash: {self.startingcash}")

    def start(self):
        super(CustomBackBroker, self).start()
        if self.persisted_positions:
            self.restore_positions(self.persisted_positions, self.cerebro.datasbyname)

    def restore_positions(self, db_positions, datasbyname):
        logger.info("データベースからポジション情報を復元中 (CustomBackBroker)...")
        for symbol, pos_data in db_positions.items():
            if symbol in datasbyname:
                data_feed = datasbyname[symbol]
                size = pos_data.get('size')
                price = pos_data.get('price')
                if size is not None and price is not None:
                    self.positions[data_feed].size = size
                    self.positions[data_feed].price = price
                    self.cash -= size * price # 現金を調整
                    logger.info(f"  -> 復元完了: {symbol}, Size: {size}, Price: {price}, Cash Adjusted: {-size * price}")
                else:
                    logger.warning(f"  -> 復元失敗: {symbol} のデータが不完全です。{pos_data}")
            else:
                logger.warning(f"  -> 復元失敗: 銘柄 '{symbol}' に対応するデータフィードが見つかりません。")
""",

    "realtrade/live/sbi_broker.py": """import backtrader as bt
import logging
from backtrader.position import Position

logger = logging.getLogger(__name__)

class SBIBroker(bt.brokers.BrokerBase):
    def __init__(self, store, persisted_positions=None):
        super(SBIBroker, self).__init__()
        self.store = store
        self.orders = []
        self.persisted_positions = persisted_positions or {}
        logger.info("SBIBrokerを初期化しました。")

    def start(self):
        super(SBIBroker, self).start()
        self.cash = self.store.get_cash()
        self.value = self.store.get_value()
        logger.info(f"Brokerを開始しました。現金: {self.cash}, 資産価値: {self.value}")
        if self.persisted_positions:
            self.restore_positions(self.persisted_positions, self.cerebro.datasbyname)

    def restore_positions(self, db_positions, datasbyname):
        logger.info("データベースからポジション情報を復元中 (SBIBroker)...")
        for symbol, pos_data in db_positions.items():
            if symbol in datasbyname:
                data_feed = datasbyname[symbol]
                size = pos_data.get('size')
                price = pos_data.get('price')
                if size is not None and price is not None:
                    pos = self.positions.get(data_feed, Position())
                    pos.size = size
                    pos.price = price
                    self.positions[data_feed] = pos
                    self.cash -= size * price # 現金を調整
                    logger.info(f"  -> 復元完了: {symbol}, Size: {size}, Price: {price}, Cash Adjusted: {-size * price}")
                else:
                    logger.warning(f"  -> 復元失敗: {symbol} のデータが不完全です。{pos_data}")
            else:
                logger.warning(f"  -> 復元失敗: 銘柄 '{symbol}' に対応するデータフィードが見つかりません。")

    def buy(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, **kwargs):
        order = super().buy(owner, data, size, price, plimit, exectype, valid, tradeid, oco, trailamount, trailpercent, **kwargs)
        order.api_id = self.store.place_order(order)
        self.orders.append(order)
        self.notify(order)
        return order

    def sell(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, **kwargs):
        order = super().sell(owner, data, size, price, plimit, exectype, valid, tradeid, oco, trailamount, trailpercent, **kwargs)
        order.api_id = self.store.place_order(order)
        self.orders.append(order)
        self.notify(order)
        return order

    def cancel(self, order):
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            self.store.cancel_order(order.api_id)
            order.cancel()
            self.notify(order)
        return order
""",

    "realtrade/analyzer.py": """import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class TradePersistenceAnalyzer(bt.Analyzer):
    params = (('state_manager', None),)
    
    def __init__(self):
        if not self.p.state_manager: raise ValueError("StateManagerがAnalyzerに渡されていません。")
        self.state_manager = self.p.state_manager
        logger.info("TradePersistenceAnalyzer initialized.")

    def notify_trade(self, trade):
        super().notify_trade(trade)
        symbol = trade.data._name
        
        if trade.isclosed:
            # ポジションが決済されたので、DBから削除する
            self.state_manager.delete_position(symbol)
            logger.info(f"StateManager: ポジションをDBから削除: {symbol}")
        
        elif trade.isopen:
            # ポジションが新規にオープンされたので、DBに保存/更新する
            pos = self.strategy.broker.getposition(trade.data)
            if pos.size != 0:
                entry_dt = bt.num2date(trade.dtopen).isoformat()
                self.state_manager.save_position(symbol, pos.size, pos.price, entry_dt)
                logger.info(f"StateManager: ポジションをDBに保存/更新: {symbol} (New Size: {pos.size})")
            else:
                # ポジションクローズ時にisopenが呼ばれることがあるため、その場合は無視する
                logger.info(f"StateManager: isopen通知を受けましたがポジションサイズが0のため無視します: {symbol}")
""",
    
    # --- 以下、変更のないファイル ---
    "realtrade/live/__init__.py": """# このディレクトリは、実際の証券会社APIと連携するためのモジュールを含みます。
""",
    "realtrade/live/sbi_store.py": """import logging

logger = logging.getLogger(__name__)

class SBIStore:
    def __init__(self, api_key, api_secret, paper_trading=True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper_trading = paper_trading
        logger.info(f"SBIStoreを初期化しました。ペーパートレード: {self.paper_trading}")

    def get_cash(self): return 10000000 
    def get_value(self): return 10000000
    
    def get_positions(self):
        # 本来はAPIから取得する。ここではダミーを返す。
        logger.info("【API連携】口座のポジション情報を取得します... (現在はダミー)")
        return [] 
    
    def place_order(self, order):
        logger.info(f"【API連携】注文を送信します: {order}")
        return f"api-order-{id(order)}"
        
    def cancel_order(self, order_id):
        logger.info(f"【API連携】注文キャンセルを送信します: OrderID={order_id}")

    def get_historical_data(self, dataname, timeframe, compression, period):
        logger.info(f"【API連携】履歴データを取得します: {dataname} ({period}本)")
        return None
""",
    "realtrade/live/sbi_data.py": """import backtrader as bt
import pandas as pd
from datetime import datetime
import time
import threading
import random
import logging

logger = logging.getLogger(__name__)

class SBIData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1),)

    def __init__(self):
        store = self.p.store
        if not store:
            raise ValueError("SBIDataにはstoreの指定が必要です。")
        symbol = self.p.dataname
        df = store.get_historical_data(dataname=symbol, timeframe=self.p.timeframe, compression=self.p.compression, period=200)
        if df is None or df.empty:
            logger.warning(f"[{symbol}] 履歴データがありません。空のフィードを作成します。")
            df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
            df['openinterest'] = 0.0
        self.p.dataname = df
        super(SBIData, self).__init__()
        self.symbol_str = symbol
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        super(SBIData, self).start()
        logger.info(f"[{self.symbol_str}] リアルタイムデータ取得スレッドを開始します...")
        self._thread = threading.Thread(target=self._run)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.symbol_str}] リアルタイムデータ取得スレッドを停止します...")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        super(SBIData, self).stop()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                time.sleep(5)
                last_close = self.close[-1] if len(self.close) > 0 else 1000
                new_open = self.open[0] = self.close[0] if len(self.open) > 0 else last_close
                new_close = new_open * (1 + random.uniform(-0.005, 0.005))
                self.lines.datetime[0] = bt.date2num(datetime.now())
                self.lines.open[0] = new_open
                self.lines.high[0] = max(new_open, new_close) * (1 + random.uniform(0, 0.002))
                self.lines.low[0] = min(new_open, new_close) * (1 - random.uniform(0, 0.002))
                self.lines.close[0] = new_close
                self.lines.volume[0] = random.randint(100, 5000)
                self.put_notification(self.LIVE)
            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}")
                time.sleep(10)
""",

    "realtrade/live/yahoo_store.py": """import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

class YahooStore:
    def __init__(self, **kwargs):
        logger.info("YahooStoreを初期化しました。")

    def get_cash(self): return 0
    def get_value(self): return 0
    def get_positions(self): return []
    def place_order(self, order): return None
    def cancel_order(self, order_id): return None

    def get_historical_data(self, dataname, period, interval='1m'):
        logger.info(f"【Yahoo Finance】履歴データを取得します: {dataname} ({period} {interval})")
        ticker = f"{dataname}.T"
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
            if df.empty:
                logger.warning(f"{ticker}のデータ取得に失敗しました。")
                return pd.DataFrame()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]
            df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df['openinterest'] = 0.0
            logger.info(f"{dataname}の履歴データを{len(df)}件取得しました。")
            return df
        except Exception as e:
            logger.error(f"{ticker}のデータ取得中にエラーが発生しました: {e}")
            return pd.DataFrame()
""",

    "realtrade/live/yahoo_data.py": """import backtrader as bt
from datetime import datetime
import time
import threading
import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

class YahooData(bt.feeds.PandasData):
    params = (('store', None), ('timeframe', bt.TimeFrame.Minutes), ('compression', 1),)

    def __init__(self):
        store = self.p.store
        if not store: raise ValueError("YahooDataにはstoreの指定が必要です。")
        symbol = self.p.dataname
        df = store.get_historical_data(dataname=symbol, period='7d', interval='1m')
        if df.empty:
            logger.warning(f"[{symbol}] 履歴データがありません。空のフィードを作成します。")
            df = pd.DataFrame(index=pd.to_datetime([]), columns=['open', 'high', 'low', 'close', 'volume', 'openinterest'])
        self.p.dataname = df
        super(YahooData, self).__init__()
        self.symbol_str = symbol
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        super(YahooData, self).start()
        logger.info(f"[{self.symbol_str}] リアルタイムデータ取得スレッドを開始します...")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        logger.info(f"[{self.symbol_str}] リアルタイムデータ取得スレッドを停止します...")
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        super(YahooData, self).stop()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                time.sleep(60)
                ticker = f"{self.symbol_str}.T"
                df = yf.download(ticker, period='1d', interval='1m', progress=False, auto_adjust=False)
                if df.empty: continue
                if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]
                if df.columns.duplicated().any():
                    df = df.loc[:, ~df.columns.duplicated(keep='first')]
                if len(self.lines.datetime) > 0 and self.lines.datetime[-1] >= bt.date2num(df.index[-1].to_pydatetime()):
                    continue
                latest_bar = df.iloc[-1]
                self.lines.datetime[0] = bt.date2num(latest_bar.name.to_pydatetime())
                self.lines.open[0] = latest_bar['Open'].item()
                self.lines.high[0] = latest_bar['High'].item()
                self.lines.low[0] = latest_bar['Low'].item()
                self.lines.close[0] = latest_bar['Close'].item()
                self.lines.volume[0] = latest_bar['Volume'].item()
                self.lines.openinterest[0] = 0.0
                self.put_notification(self.LIVE)
                logger.debug(f"[{self.symbol_str}] 新しいデータを追加: {latest_bar.name}")
            except Exception as e:
                logger.error(f"データ取得スレッドでエラーが発生: {e}")
                time.sleep(60)
""",

    "realtrade/state_manager.py": """import sqlite3
import logging
import os

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self._create_tables()
            logger.info(f"データベースに接続しました: {db_path}")
        except sqlite3.Error as e:
            logger.critical(f"データベース接続エラー: {e}")
            raise

    def _create_tables(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY, 
                    size REAL NOT NULL,
                    price REAL NOT NULL, 
                    entry_datetime TEXT NOT NULL
                )
            ''')
            self.conn.commit()
        except sqlite3.Error as e: logger.error(f"テーブル作成エラー: {e}")

    def close(self):
        if self.conn: self.conn.close(); logger.info("データベース接続をクローズしました。")

    def save_position(self, symbol, size, price, entry_datetime):
        sql = "INSERT OR REPLACE INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)"
        try:
            cursor = self.conn.cursor(); cursor.execute(sql, (str(symbol), size, price, entry_datetime)); self.conn.commit()
        except sqlite3.Error as e: logger.error(f"ポジション保存エラー: {e}")

    def load_positions(self):
        positions = {}
        sql = "SELECT symbol, size, price, entry_datetime FROM positions"
        try:
            cursor = self.conn.cursor()
            for row in cursor.execute(sql):
                positions[row[0]] = {'size': row[1], 'price': row[2], 'entry_datetime': row[3]}
            logger.info(f"{len(positions)}件のポジションをDBからロードしました。")
            return positions
        except sqlite3.Error as e:
            logger.error(f"ポジション読み込みエラー: {e}"); return {}

    def delete_position(self, symbol):
        sql = "DELETE FROM positions WHERE symbol = ?"
        try:
            cursor = self.conn.cursor(); cursor.execute(sql, (str(symbol),)); self.conn.commit()
        except sqlite3.Error as e: logger.error(f"ポジション削除エラー: {e}")
""",

    "realtrade/mock/__init__.py": """# シミュレーションモード用のモック実装パッケージ
""",

    "realtrade/mock/data_fetcher.py": """from realtrade.data_fetcher import DataFetcher
import backtrader as bt
import pandas as pd
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

class RealtimeDataFeed(bt.feeds.PandasData):
    pass

class MockDataFetcher(DataFetcher):
    def start(self): 
        logger.info("MockDataFetcher: 起動しました。")
    
    def stop(self): 
        logger.info("MockDataFetcher: 停止しました。")

    def get_data_feed(self, symbol):
        if self.data_feeds.get(symbol) is None:
            df = self._generate_dummy_data(symbol, 200)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]

    def _generate_dummy_data(self, symbol, period):
        logger.info(f"MockDataFetcher: ダミー履歴データ生成 - 銘柄:{symbol}, 期間:{period}本")
        dates = pd.date_range(end=datetime.now(), periods=period, freq='1min').tz_localize(None)
        start_price, prices = np.random.uniform(1000, 5000), []
        current_price = start_price
        for _ in range(period):
            current_price *= (1 + np.random.normal(loc=0.0001, scale=0.01))
            prices.append(current_price)
        
        df = pd.DataFrame(index=dates)
        df['open'] = prices
        df['close'] = [p * (1 + np.random.normal(0, 0.005)) for p in prices]
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.005, size=period))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.005, size=period))
        df['volume'] = np.random.randint(100, 10000, size=period)
        return df
""",

    "realtrade/data_fetcher.py": """import abc
import backtrader as bt

class DataFetcher(metaclass=abc.ABCMeta):
    def __init__(self, symbols, config):
        self.symbols = symbols
        self.config = config
        self.data_feeds = {s: None for s in symbols}

    @abc.abstractmethod
    def start(self): raise NotImplementedError
    @abc.abstractmethod
    def stop(self): raise NotImplementedError
    @abc.abstractmethod
    def get_data_feed(self, symbol): raise NotImplementedError
""",

    "logger_setup.py": """import logging
import os
from datetime import datetime

def setup_logging(config_module, log_prefix):
    log_dir = config_module.LOG_DIR
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    if log_prefix == 'backtest':
        log_filename = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"
    else:
        log_filename = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d')}.log"
    log_filepath = os.path.join(log_dir, log_filename)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=config_module.LOG_LEVEL,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, encoding='utf-8'),
                                  logging.StreamHandler()])
    print(f"ロガーをセットアップしました。モード: {log_prefix}, ログファイル: {log_filepath}")""",
}

def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        
        content = content.strip()
        if not content: continue
        
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"ファイルを作成/更新しました: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("リアルタイムトレード用のプロジェクトファイル生成を開始します...")
    create_files(project_files)
    print("\nプロジェクトファイルの生成が完了しました。")
    print("\n【重要】次の手順で動作確認を行ってください:")
    print("1. このスクリプト(`create_project_files_realtime.py`)を実行して、最新のファイルを生成します。")
    print("2. `pip install -r requirements_realtime.txt` を実行して、ライブラリをインストールします。")
    print("3. (テスト) `realtrade/db/realtrade_state.db` に手動でテストポジションを追加します。")
    print("   例: INSERT INTO positions (symbol, size, price, entry_datetime) VALUES ('7270', 100, 5000, '2025-07-01T10:00:00');")
    print("4. `config_realtime.py` で `LIVE_TRADING=True` を設定し、`run_realtrade.py` を実行します。")
    print("5. 起動ログに『状態復元: 既存ポジションを検出...』というメッセージが表示されれば成功です")
