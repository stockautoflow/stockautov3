# ==============================================================================
# ファイル: create_project_files.py
# 説明: このスクリプトは、戦略ロジックをYAMLファイルで定義できるように改善した
#       株自動トレードシステムの全てのファイルを生成します。
# バージョン: v78.0
# 主な変更点:
#   - btrader_strategy.py:
#     - 文字列内のdocstringが原因で発生するSyntaxErrorを修正。
#     - ライブトレード用の決済ロジック（利確・トレーリングストップ）を実装。
#       - __init__に `live_trading` パラメータを追加。
#       - nextメソッドをリファクタリングし、エントリーチェックと決済チェックを分離。
#       - ライブトレード時に価格を監視し、条件を満たした場合に決済注文を出す
#         `_check_live_exit_conditions` メソッドを追加。
# ==============================================================================
import os

project_files = {
    "requirements.txt": """backtrader
pandas==2.1.4
numpy==1.26.4
PyYAML==6.0.1
matplotlib
plotly==5.18.0
Flask==3.0.0
schedule
python-dotenv
yfinance""",

    "email_config.yml": """ENABLED: False # メール通知を有効にする場合は True に変更
SMTP_SERVER: "smtp.gmail.com"
SMTP_PORT: 587
SMTP_USER: "your_email@gmail.com"
SMTP_PASSWORD: "your_app_password" # Gmailの場合はアプリパスワード
RECIPIENT_EMAIL: "recipient_email@example.com"
""",

    "config_backtrader.py": """import os
import logging

# --- ディレクトリ設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'backtest_results')
LOG_DIR = os.path.join(BASE_DIR, 'log')
REPORT_DIR = os.path.join(RESULTS_DIR, 'report')
CHART_DIR = os.path.join(RESULTS_DIR, 'chart')

# --- バックテスト設定 ---
INITIAL_CAPITAL = 50000000000000 # 初期資金
COMMISSION_PERC = 0 #0.0005 # 0.05%
SLIPPAGE_PERC = 0.0002 # 0.02%

# --- ロギング設定 ---
LOG_LEVEL = logging.INFO # INFO or DEBUG
""",

    "strategy.yml": """strategy_name: "Dynamic Timeframe Strategy"
trading_mode:
  long_enabled: True
  short_enabled: True

# === ▼▼▼ データ読み込み設定 ▼▼▼ ===
# source_type: 'resample' または 'direct' を指定
#   resample: shortのデータからリサンプリングして生成 (デフォルト)
#   direct: file_patternで指定されたファイルを直接読み込む
# timeframe / compression: Backtraderがデータを解釈するために必要
# file_pattern: direct指定時に読み込むファイル名。{symbol}が銘柄コードに置換される。
timeframes:
  long:
    source_type: direct
    timeframe: "Days"
    compression: 1
    file_pattern: "{symbol}_D_*.csv"
  medium:
    source_type: direct
    timeframe: "Minutes"
    compression: 60
    file_pattern: "{symbol}_60m_*.csv"
  short:
    # 短期データは常に直接読み込み。source_typeは不要。
    timeframe: "Minutes"
    compression: 5

# === ▲▲▲ データ読み込み設定ここまで ▲▲▲ ===

entry_conditions:
  long:
    - { timeframe: "long", indicator: { name: "ema", params: { period: 20 } }, compare: ">", target: { type: "data", value: "close" } }
    - { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "<", target: { type: "values", value: [40] } }
    - { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }
  short:
   - { timeframe: "long", indicator: { name: "ema", params: { period: 20 } }, compare: "<", target: { type: "data", value: "close" } }
   - { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: ">", target: { type: "values", value: [60] } }
   - { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

exit_conditions:
  take_profit:
    type: "atr_multiple"
    timeframe: "short"
    params: { period: 14, multiplier: 5.0 }
  stop_loss:
    type: "atr_stoptrail"
    timeframe: "short"
    params: { period: 14, multiplier: 2.5 }

sizing:
  risk_per_trade: 0.01 # 1トレードあたりのリスク(資金に対する割合)
  max_investment_per_trade: 10000000 # 1トレードあたりの最大投資額(円)

indicators:
  long_ema_period: 200
  medium_rsi_period: 14
  short_ema_fast: 10
  short_ema_slow: 25
  atr_period: 14
  adx: { period: 14 }
  macd: { fast_period: 12, slow_period: 26, signal_period: 9 }
  stochastic: { period: 14, period_dfast: 3, period_dslow: 3 }
  bollinger: { period: 20, devfactor: 2.0 }
  sma: { fast_period: 5, slow_period: 20 }
  vwap: { enabled: True }
  ichimoku: { tenkan_period: 9, kijun_period: 26, senkou_span_b_period: 52, chikou_period: 26 }
""",

    "logger_setup.py": """import logging
import os
from datetime import datetime

def setup_logging(config_module, log_prefix):
    \"\"\"
    バックテストとリアルタイムトレードで共用できる汎用ロガーをセットアップします。
    
    :param config_module: 'config_backtrader' または 'config_realtrade' モジュール
    :param log_prefix: 'backtest' または 'realtime'
    \"\"\"
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

    "notifier.py": """import smtplib, yaml, logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

def load_email_config():
    try:
        with open('email_config.yml', 'r', encoding='utf-8') as f: return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"email_config.ymlの読み込み中にエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body):
    email_config = load_email_config()
    if not email_config.get("ENABLED"): return
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = email_config["SMTP_USER"], email_config["RECIPIENT_EMAIL"], subject
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
""",

    "btrader_strategy.py": """import backtrader as bt
import logging
import inspect
import yaml

# === カスタムインジケーター定義 (変更なし) ===
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
        ('live_trading', False), # [追加] ライブトレードモードかどうかのフラグ
    )

    def __init__(self):
        self.live_trading = self.p.live_trading
        
        # どのファイルから戦略を読み込むかを決定する
        if self.p.strategy_catalog and self.p.strategy_assignments:
            symbol_str = self.data._name
            symbol = int(symbol_str) if symbol_str.isdigit() else symbol_str
            strategy_name = self.p.strategy_assignments.get(str(symbol))
            if not strategy_name:
                raise ValueError(f"銘柄 {symbol} に戦略が割り当てられていません。")
            
            try:
                with open('strategy.yml', 'r', encoding='utf-8') as f:
                    base_strategy = yaml.safe_load(f)
            except FileNotFoundError:
                raise FileNotFoundError("共通基盤ファイル 'strategy.yml' が見つかりません。")

            entry_strategy_def = self.p.strategy_catalog.get(strategy_name)
            if not entry_strategy_def:
                raise ValueError(f"エントリー戦略カタログ 'strategies.yml' に '{strategy_name}' が見つかりません。")
            
            import copy
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
        
        # --- 注文・状態管理用の変数を初期化 ---
        self.entry_order = None
        self.exit_orders = [] # ライブトレードでは成行決済注文、バックテストではネイティブ注文を格納
        self.entry_reason = ""
        self.entry_reason_for_trade = ""
        self.executed_size = 0
        
        # --- ライブトレード用の決済価格管理 ---
        self.risk_per_share = 0.0 # エントリー時に計算
        self.tp_price = 0.0       # エントリー時に計算
        self.sl_price = 0.0       # ポジション保有中に更新

        self.current_position_entry_dt = None

    # (変更なし) _get_indicator_key, _create_indicators, _evaluate_condition, _check_all_conditions
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
        if order.status in [order.Submitted, order.Accepted]:
            return

        # エントリー注文の約定/失敗を処理
        if self.entry_order and self.entry_order.ref == order.ref:
            if order.status == order.Completed:
                self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
                
                # バックテストモードでは、ネイティブの決済注文を発注
                if not self.live_trading:
                    self._place_native_exit_orders()
                # ライブモードでは、決済価格を計算・保持して監視開始
                else:
                    is_long = order.isbuy()
                    entry_price = order.executed.price
                    # self.risk_per_share と self.tp_price はエントリー直前に計算済み
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
                    self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, Initial SL={self.sl_price:.2f}")

            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log(f"エントリー注文失敗/キャンセル: {order.getstatusname()}")
                self.sl_price, self.tp_price = 0.0, 0.0 # 決済価格をリセット
            
            self.entry_order = None # エントリー注文の参照をクリア

        # 決済注文の約定/失敗を処理
        elif self.exit_orders and self.exit_orders[0].ref == order.ref:
            if order.status == order.Completed:
                self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
                self.sl_price, self.tp_price = 0.0, 0.0
                self.exit_orders = []
            elif order.status in [order.Canceled, order.Margin, order.Rejected]:
                self.log(f"決済注文失敗/キャンセル: {order.getstatusname()}")
                self.exit_orders = [] # 再度、決済注文を出せるようにクリア
    
    # (変更なし) notify_trade
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
        # バックテスト用のネイティブ決済注文(OCO)を発注する
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
        # ライブトレード用のクライアントサイド決済ロジック
        pos = self.getposition()
        is_long = pos.size > 0
        current_price = self.data.close[0]
        
        # --- 利確(Take Profit)チェック ---
        if self.tp_price != 0:
            if (is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price):
                self.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
                exit_order = self.close() # 成行で決済
                self.exit_orders.append(exit_order)
                return

        # --- 損切(ATR Trailing Stop)チェック ---
        if self.sl_price != 0:
            # 1. 損切り価格にヒットしたかチェック
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                self.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                exit_order = self.close() # 成行で決済
                self.exit_orders.append(exit_order)
                return

            # 2. ヒットしていなければ、トレーリングストップ価格を更新
            new_sl_price = 0
            if is_long:
                new_sl_price = current_price - self.risk_per_share
                if new_sl_price > self.sl_price:
                    self.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                    self.sl_price = new_sl_price
            else: # is_short
                new_sl_price = current_price + self.risk_per_share
                if new_sl_price < self.sl_price:
                    self.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}")
                    self.sl_price = new_sl_price

    def _check_entry_conditions(self):
        # エントリー条件をチェックし、注文を発注する
        exit_conditions = self.strategy_params['exit_conditions']
        sl_cond = exit_conditions['stop_loss']
        atr_key = self._get_indicator_key(sl_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in sl_cond.get('params', {}).items() if k!='multiplier'})
        if not self.indicators.get(atr_key):
             self.log(f"ATRインジケーター '{atr_key}' が見つかりません。")
             return
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
                    self.log(f"ATRインジケーター '{tp_key}' が見つかりません。")
                    self.tp_price = 0 
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
        # エントリー注文が保留中なら常に待機
        if self.entry_order:
            return

        # 【変更】ライブモードで、かつクライアントサイドの決済注文が
        # 保留中の場合のみ待機するように修正
        if self.live_trading and self.exit_orders:
            return

        # ポジションがある場合は決済条件をチェック
        if self.getposition().size:
            if self.live_trading:
                self._check_live_exit_conditions()
            # バックテストモードではネイティブ注文に任せるため、これ以降の
            # エントリーチェックは行わずリターンする (この部分は正しい)
            return

        # ポジションがない場合はエントリー条件をチェック
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
""",

    "report_generator.py": """import pandas as pd
import config_backtrader as config
from datetime import datetime

def _format_condition_for_report(cond):
    tf = cond['timeframe'][0].upper()
    cond_type = cond.get('type')

    if cond_type == 'crossover' or cond_type == 'crossunder':
        i1 = cond['indicator1']; i2 = cond['indicator2']
        p1, p2 = ",".join(map(str, i1.get('params', {}).values())), ",".join(map(str, i2.get('params', {}).values()))
        op = " crosses over " if cond_type == 'crossover' else " crosses under "
        return f"{tf}: {i1['name']}({p1}){op}{i2['name']}({p2})"

    ind_def, ind_str = cond['indicator'], f"{cond['indicator']['name']}({','.join(map(str, cond['indicator'].get('params', {}).values()))})"
    comp_str = 'is between' if cond['compare'] == 'between' else cond['compare']
    tgt, tgt_type, tgt_str = cond['target'], cond['target'].get('type'), ""

    if tgt_type == 'data': tgt_str = tgt.get('value', '')
    elif tgt_type == 'indicator':
        tgt_ind_def = tgt.get('indicator', {})
        tgt_params_str = ",".join(map(str, tgt_ind_def.get('params', {}).values()))
        tgt_str = f"{tgt_ind_def.get('name', '')}({tgt_params_str})"
    elif tgt_type == 'values':
        value = tgt.get('value')
        tgt_str = f"{value[0]} and {value[1]}" if isinstance(value, list) and len(value) > 1 else str(value)

    return f"{tf}: {ind_str} {comp_str} {tgt_str}"

def _format_exit_for_report(exit_cond):
    p, tf = exit_cond.get('params', {}), exit_cond.get('timeframe','?')[0]
    mult, period = p.get('multiplier'), p.get('period')
    if exit_cond.get('type') == 'atr_multiple': return f"Fixed ATR(t:{tf}, p:{period}) * {mult}"
    if exit_cond.get('type') == 'atr_stoptrail': return f"Native StopTrail ATR(t:{tf}, p:{period}) * {mult}"
    return "Unknown"

def generate_report(all_results, p, start_date, end_date):
    total_net = sum(r['pnl_net'] for r in all_results)
    total_won, total_lost = sum(r['gross_won'] for r in all_results), sum(r['gross_lost'] for r in all_results)
    total_trades, total_win = sum(r['total_trades'] for r in all_results), sum(r['win_trades'] for r in all_results)
    win_rate = (total_win / total_trades) * 100 if total_trades > 0 else 0
    pf = abs(total_won / total_lost) if total_lost != 0 else float('inf')
    avg_profit = total_won / total_win if total_win > 0 else 0
    avg_loss = total_lost / (total_trades - total_win) if (total_trades - total_win) > 0 else 0
    rr = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')

    long_c = "Long: " + " AND ".join([_format_condition_for_report(c) for c in p.get('entry_conditions',{}).get('long',[])]) if p.get('trading_mode',{}).get('long_enabled') else ""
    short_c = "Short: " + " AND ".join([_format_condition_for_report(c) for c in p.get('entry_conditions',{}).get('short',[])]) if p.get('trading_mode',{}).get('short_enabled') else ""
    tp_desc = _format_exit_for_report(p.get('exit_conditions',{}).get('take_profit',{})) if p.get('exit_conditions',{}).get('take_profit') else "N/A"
    
    return pd.DataFrame({
        '項目': ["分析日時", "分析期間", "初期資金", "トレード毎リスク", "手数料", "スリッページ", "戦略名", "エントリーロジック", "損切りロジック", "利確ロジック", "---", "純利益", "総利益", "総損失", "PF", "勝率", "総トレード数", "勝トレード", "負トレード", "平均利益", "平均損失", "RR比"],
        '結果': [datetime.now().strftime('%Y-%m-%d %H:%M'), f"{start_date.strftime('%y/%m/%d')}-{end_date.strftime('%y/%m/%d')}", f"¥{config.INITIAL_CAPITAL:,.0f}", f"{p.get('sizing',{}).get('risk_per_trade',0):.1%}", f"{config.COMMISSION_PERC:.3%}", f"{config.SLIPPAGE_PERC:.3%}", p.get('strategy_name','N/A'), " | ".join(filter(None, [long_c, short_c])), _format_exit_for_report(p.get('exit_conditions',{}).get('stop_loss',{})), tp_desc, "---", f"¥{total_net:,.0f}", f"¥{total_won:,.0f}", f"¥{total_lost:,.0f}", f"{pf:.2f}", f"{win_rate:.2f}%", total_trades, total_win, total_trades-total_win, f"¥{avg_profit:,.0f}", f"¥{avg_loss:,.0f}", f"{rr:.2f}"],
    })
""",

    "run_backtrader.py": """import backtrader as bt
import pandas as pd
import os
import glob
import yaml
import logging
from datetime import datetime
import logger_setup
import config_backtrader as config
import config_backtrader as config
import btrader_strategy
import notifier
import report_generator

logger = logging.getLogger(__name__)

class TradeList(bt.Analyzer):
    def __init__(self): self.trades, self.symbol = [], ""
    def start(self): self.symbol = self.strategy.data._name
    def notify_trade(self, trade):
        if not trade.isclosed: return
        size, pnl = abs(getattr(trade, 'executed_size', 0)), trade.pnl
        exit_price = (trade.value + pnl) / size if size > 0 else trade.price
        self.trades.append({'銘柄': self.symbol, '方向': 'BUY' if trade.long else 'SELL', '数量': size,
                            'エントリー価格': trade.price, 'エントリー日時': bt.num2date(trade.dtopen).replace(tzinfo=None).isoformat(), 'エントリー根拠': getattr(trade, 'entry_reason_for_trade', 'N/A'),
                            '決済価格': exit_price, '決済日時': bt.num2date(trade.dtclose).replace(tzinfo=None).isoformat(), '決済根拠': "Take Profit" if trade.pnlcomm >= 0 else "Stop Loss",
                            '損益': trade.pnl, '損益(手数料込)': trade.pnlcomm, 'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price})
    def stop(self):
        if not self.strategy.position: return
        pos, entry_price, size = self.strategy.position, self.strategy.position.price, self.strategy.position.size
        exit_price, pnl = self.strategy.data.close[0], (self.strategy.data.close[0] - entry_price) * size
        commission = (abs(size)*entry_price*config.COMMISSION_PERC) + (abs(size)*exit_price*config.COMMISSION_PERC)
        self.trades.append({'銘柄': self.symbol, '方向': 'BUY' if size > 0 else 'SELL', '数量': abs(size),
                            'エントリー価格': entry_price, 'エントリー日時': self.strategy.current_position_entry_dt.isoformat(), 'エントリー根拠': self.strategy.entry_reason,
                            '決済価格': exit_price, '決済日時': self.strategy.data.datetime.datetime(0).isoformat(), '決済根拠': "End of Backtest",
                            '損益': pnl, '損益(手数料込)': pnl - commission, 'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price})
    def get_analysis(self): return self.trades

def load_data_feed(filepath, timeframe_str, compression):
    try:
        df = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        df.columns = [x.lower() for x in df.columns]
        return bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.TFrame(timeframe_str), compression=compression)
    except Exception as e:
        logger.error(f"CSV読み込みまたはデータフィード作成で失敗: {filepath} - {e}")
        return None

def run_backtest_for_symbol(symbol, base_filepath, strategy_cls, strategy_params):
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(strategy_cls, strategy_params=strategy_params)
    
    timeframes_config = strategy_params['timeframes']
    data_feeds = {}
    
    short_tf = timeframes_config['short']
    base_data = load_data_feed(base_filepath, short_tf['timeframe'], short_tf['compression'])
    if base_data is None: return None, None, None, None
    base_data._name = symbol
    data_feeds['short'] = base_data

    for tf_name in ['medium', 'long']:
        tf_config = timeframes_config[tf_name]
        source_type = tf_config.get('source_type', 'resample')

        if source_type == 'direct':
            pattern_template = tf_config.get('file_pattern')
            if not pattern_template:
                logger.error(f"[{symbol}] {tf_name}のsource_typeが'direct'ですが、file_patternが未定義です。")
                return None, None, None, None
            
            search_pattern = os.path.join(config.DATA_DIR, pattern_template.format(symbol=symbol))
            data_files = glob.glob(search_pattern)
            if not data_files:
                logger.error(f"[{symbol}] {tf_name}用のデータファイルが見つかりません: {search_pattern}")
                return None, None, None, None
            
            data_feed = load_data_feed(data_files[0], tf_config['timeframe'], tf_config['compression'])
            if data_feed is None: return None, None, None, None
            data_feeds[tf_name] = data_feed
        
        elif source_type == 'resample':
            data_feeds[tf_name] = {'resample': True, 'config': tf_config}

    cerebro.adddata(data_feeds['short'])
    for tf_name in ['medium', 'long']:
        feed = data_feeds[tf_name]
        if isinstance(feed, dict) and feed.get('resample'):
            cfg = feed['config']
            cerebro.resampledata(data_feeds['short'], timeframe=bt.TimeFrame.TFrame(cfg['timeframe']), compression=cfg['compression'], name=tf_name)
        else:
            cerebro.adddata(feed, name=tf_name)
    
    cerebro.broker.set_cash(config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=config.COMMISSION_PERC)
    cerebro.broker.set_slippage_perc(perc=config.SLIPPAGE_PERC)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addanalyzer(TradeList, _name='tradelist')

    # --- [変更] ZeroDivisionErrorを捕捉する例外処理を追加 ---
    try:
        results = cerebro.run()
        strat = results[0]
        trade_analysis = strat.analyzers.trade.get_analysis()
        trade_list = strat.analyzers.tradelist.get_analysis()
    
        return {'symbol': symbol, 'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0),
                'gross_won': trade_analysis.get('won', {}).get('pnl', {}).get('total', 0),
                'gross_lost': trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0),
                'total_trades': trade_analysis.get('total', {}).get('total', 0),
                'win_trades': trade_analysis.get('won', {}).get('total', 0)
               }, pd.to_datetime(strat.data.datetime.date(0)), pd.to_datetime(strat.data.datetime.date(-1)), trade_list
    except ZeroDivisionError:
        logger.warning(f"銘柄 {symbol} のバックテスト中にゼロ除算エラーが発生しました。計算不能なデータが含まれている可能性があるため、この銘柄のテストをスキップします。")
        return None, None, None, None
    # -----------------------------------------------------------

def main():
    logger_setup.setup_logging(config, log_prefix='backtest')
    logger.info("--- 全銘柄バックテスト開始 ---")
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path): os.makedirs(dir_path)
        
    with open('strategy.yml', 'r', encoding='utf-8') as f: strategy_params = yaml.safe_load(f)

    short_tf_compression = strategy_params['timeframes']['short']['compression']
    base_file_pattern = f"*_{short_tf_compression}m_*.csv"
    base_csv_files = glob.glob(os.path.join(config.DATA_DIR, base_file_pattern))
    
    if not base_csv_files:
        logger.error(f"{config.DATA_DIR}にベースデータが見つかりません (パターン: {base_file_pattern})。"); return

    all_results, all_trades, all_details, start_dates, end_dates = [], [], [], [], []
    for filepath in sorted(base_csv_files):
        symbol = os.path.basename(filepath).split('_')[0]
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(symbol, filepath, btrader_strategy.DynamicStrategy, strategy_params)
        if stats:
            all_results.append(stats)
            all_trades.extend(trade_list)
            if start_date: start_dates.append(start_date)
            if end_date: end_dates.append(end_date)
            
            win_trades = stats['win_trades']
            total_trades = stats['total_trades']
            lost_trades = total_trades - win_trades
            
            win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
            pf = abs(stats['gross_won'] / stats['gross_lost']) if stats['gross_lost'] != 0 else float('inf')
            avg_win = stats['gross_won'] / win_trades if win_trades > 0 else 0
            avg_loss = stats['gross_lost'] / lost_trades if lost_trades > 0 else 0
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            
            all_details.append({
                "銘柄": stats['symbol'],
                "純利益": f"¥{stats['pnl_net']:,.2f}",
                "総利益": f"¥{stats['gross_won']:,.2f}",
                "総損失": f"¥{stats['gross_lost']:,.2f}",
                "PF": f"{pf:.2f}",
                "勝率": f"{win_rate:.2f}%",
                "総トレード数": total_trades,
                "勝トレード": win_trades,
                "負トレード": lost_trades,
                "平均利益": f"¥{avg_win:,.2f}",
                "平均損失": f"¥{avg_loss:,.2f}",
                "RR比": f"{rr:.2f}"
            })

    if not all_results or not start_dates or not end_dates:
        logger.warning("有効な結果/期間がなくレポート生成をスキップします。"); return

    report_df = report_generator.generate_report(all_results, strategy_params, min(start_dates), max(end_dates))
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    report_df.to_csv(os.path.join(config.REPORT_DIR, f"summary_{timestamp}.csv"), index=False, encoding='utf-8-sig')
    
    if all_details: 
        pd.DataFrame(all_details).to_csv(
            os.path.join(config.REPORT_DIR, f"detail_{timestamp}.csv"), 
            index=False, 
            encoding='utf-8-sig'
        )
        
    if all_trades: 
        pd.DataFrame(all_trades).to_csv(
            os.path.join(config.REPORT_DIR, f"trade_history_{timestamp}.csv"), 
            index=False, 
            encoding='utf-8-sig'
        )

    logger.info("\\\\n\\\\n★★★ 全銘柄バックテストサマリー ★★★\\\\n" + report_df.to_string())
    notifier.send_email(subject="【Backtrader】全銘柄バックテスト完了レポート", body=f"バックテストが完了しました。\\\\n\\\\n--- サマリー ---\\\\n{report_df.to_string()}")

if __name__ == '__main__':
    main()""",

    "chart_generator.py": """import os
import glob
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import yaml
import config_backtrader as config
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

price_data_cache = {}
trade_history_df = None
strategy_params = None

def load_data():
    global trade_history_df, strategy_params, price_data_cache
    
    # 戦略設定を読み込み
    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("strategy.yml が見つかりません。")
        strategy_params = {}

    # 取引履歴を読み込み
    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    if trade_history_path:
        trade_history_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
        logger.info(f"取引履歴ファイルを読み込みました: {trade_history_path}")
    else:
        trade_history_df = pd.DataFrame()
        logger.warning("取引履歴レポートが見つかりません。チャートに取引は表示されません。")
        
    # データキャッシュ処理
    price_data_cache = defaultdict(lambda: {'short': None, 'medium': None, 'long': None})
    timeframes_config = strategy_params.get('timeframes', {})
    all_symbols = get_all_symbols(config.DATA_DIR)

    for symbol in all_symbols:
        # 短期・中期・長期の各データを設定に基づいて読み込む
        for tf_name, tf_config in timeframes_config.items():
            source_type = tf_config.get('source_type', 'resample')
            
            # 短期データ、または direct 指定のデータのみを起動時に読み込む
            if tf_name == 'short' or source_type == 'direct':
                if tf_name == 'short':
                    pattern = f"{symbol}_{tf_config.get('compression', 5)}m_*.csv"
                else: 
                    pattern = tf_config.get('file_pattern', '').format(symbol=symbol)

                if not pattern:
                    logger.warning(f"[{symbol}] {tf_name}のfile_patternが未定義です。スキップします。")
                    continue
                
                search_pattern = os.path.join(config.DATA_DIR, pattern)
                data_files = glob.glob(search_pattern)

                if data_files:
                    try:
                        df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
                        df.columns = [x.lower() for x in df.columns]
                        if df.index.tz is not None:
                            df.index = df.index.tz_localize(None)
                        price_data_cache[symbol][tf_name] = df
                        logger.info(f"キャッシュ成功: {symbol} - {tf_name} ({os.path.basename(data_files[0])})")
                    except Exception as e:
                        logger.error(f"[{symbol}] {tf_name}のデータ読み込みに失敗: {data_files[0]} - {e}")
                else:
                    logger.warning(f"データファイルが見つかりません: {search_pattern}")

def find_latest_report(report_dir, prefix):
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_all_symbols(data_dir):
    file_pattern = os.path.join(data_dir, f"*_*.csv")
    files = glob.glob(file_pattern)
    return sorted(list(set(os.path.basename(f).split('_')[0] for f in files if '_' in os.path.basename(f))))

def get_trades_for_symbol(symbol):
    if trade_history_df is None or trade_history_df.empty:
        return pd.DataFrame()
    return trade_history_df[trade_history_df['銘柄'] == int(symbol)].copy()

def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    ohlc_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    return df.resample(rule, label='right', closed='right').agg(ohlc_dict).dropna()

def add_vwap(df):
    df['date'] = df.index.date
    df['typical_price_volume'] = ((df['high'] + df['low'] + df['close']) / 3) * df['volume']
    df['cumulative_volume'] = df.groupby('date')['volume'].cumsum()
    df['cumulative_tpv'] = df.groupby('date')['typical_price_volume'].cumsum()
    df['vwap'] = df['cumulative_tpv'] / df['cumulative_volume']
    df.drop(['date', 'typical_price_volume', 'cumulative_volume', 'cumulative_tpv'], axis=1, inplace=True)
    return df

def add_atr(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = tr.ewm(alpha=1/period, adjust=False).mean()
    return df

def add_adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    up_move = high - high.shift()
    down_move = low.shift() - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-9)
    df['adx'] = dx.ewm(alpha=1/period, adjust=False).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    return df

def add_ichimoku(df, p):
    high, low, close = df['high'], df['low'], df['close']
    df['tenkan_sen'] = (high.rolling(window=p['tenkan_period']).max() + low.rolling(window=p['tenkan_period']).min()) / 2
    df['kijun_sen'] = (high.rolling(window=p['kijun_period']).max() + low.rolling(window=p['kijun_period']).min()) / 2
    df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(p['kijun_period'])
    df['senkou_span_b'] = ((high.rolling(window=p['senkou_span_b_period']).max() + low.rolling(window=p['senkou_span_b_period']).min()) / 2).shift(p['kijun_period'])
    df['chikou_span'] = close.shift(-p['chikou_period'])
    return df

def generate_chart_json(symbol, timeframe_name, indicator_params):
    # --- ▼▼▼ チャート生成ロジック修正 ▼▼▼ ---
    p_ind_ui = indicator_params
    p_tf_def = strategy_params.get('timeframes', {})
    tf_config = p_tf_def.get(timeframe_name, {})
    source_type = tf_config.get('source_type', 'resample')

    df = None
    title = f"{symbol} - {timeframe_name}"

    # 1. 表示するデータフレームを決定
    if timeframe_name == 'short' or source_type == 'direct':
        df = price_data_cache.get(symbol, {}).get(timeframe_name)
        if df is not None:
             title = f"{symbol} {timeframe_name.capitalize()}-Term (Direct)"
    elif source_type == 'resample':
        base_df = price_data_cache.get(symbol, {}).get('short')
        if base_df is not None:
            timeframe = tf_config.get('timeframe', 'Minutes')
            compression = tf_config.get('compression', 60)
            rule_map = {'Minutes': 'T', 'Days': 'D', 'Weeks': 'W', 'Months': 'M'}
            rule = f"{compression}{rule_map.get(timeframe, 'T')}"
            df = resample_ohlc(base_df, rule)
            title = f"{symbol} {timeframe_name.capitalize()}-Term (Resampled from Short)"
        
    if df is None or df.empty:
        logger.warning(f"チャート生成用のデータが見つかりません: {symbol} - {timeframe_name}")
        return {}

    # 2. インジケーターを計算
    sub_plots = defaultdict(bool)
    
    # 2-1. UIで有効になっているインジケーターを計算
    df = add_adx(df, p_ind_ui['adx']['period']); sub_plots['adx'] = True
    df = add_atr(df, p_ind_ui['atr_period']); sub_plots['atr'] = True
    p = p_ind_ui['sma']; df['sma_fast'] = df['close'].rolling(p['fast_period']).mean(); df['sma_slow'] = df['close'].rolling(p['slow_period']).mean()
    p = p_ind_ui['bollinger']; df['bb_middle'] = df['close'].rolling(p['period']).mean(); df['bb_std'] = df['close'].rolling(p['period']).std(); df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * p['devfactor']); df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * p['devfactor'])
    
    p = p_ind_ui['macd']
    exp1 = df['close'].ewm(span=p['fast_period'], adjust=False).mean()
    exp2 = df['close'].ewm(span=p['slow_period'], adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=p['signal_period'], adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']; sub_plots['macd'] = True
    
    p = p_ind_ui['stochastic']
    low_min = df['low'].rolling(window=p['period']).min()
    high_max = df['high'].rolling(window=p['period']).max()
    k_fast = 100 * (df['close'] - low_min) / (high_max - low_min).replace(0, 1e-9)
    df['stoch_k'] = k_fast.rolling(window=p['period_dfast']).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=p['period_dslow']).mean(); sub_plots['stoch'] = True
    
    p = p_ind_ui['medium_rsi_period']
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=p).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
    rs = gain / loss.replace(0, 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs)); sub_plots['rsi'] = True
    
    if p_ind_ui.get('vwap', {}).get('enabled', False): df = add_vwap(df);
    df = add_ichimoku(df, p_ind_ui['ichimoku'])

    # 3. チャート描画
    active_subplots = [k for k, v in sub_plots.items() if v]
    rows = 1 + len(active_subplots)
    specs = [[{"secondary_y": True}]] + [[{} for _ in range(1)] for _ in active_subplots]
    main_height = max(0.4, 1.0 - (0.15 * len(active_subplots)))
    row_heights = [main_height] + [(1 - main_height) / len(active_subplots) if active_subplots else 0] * len(active_subplots)

    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, specs=specs, row_heights=row_heights)

    # 3-1. メインチャート (OHLC, Volume, インジケーター)
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker=dict(color=volume_colors, opacity=0.3)), secondary_y=True, row=1, col=1)

    p = p_ind_ui['bollinger']; fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, fillcolor='rgba(128,128,128,0.1)', fill='tonexty', hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], mode='lines', name=f"BB({p['period']},{p['devfactor']})", line=dict(color='gray', width=0.7, dash='dash'), connectgaps=True), row=1, col=1)
    p = p_ind_ui['sma']; fig.add_trace(go.Scatter(x=df.index, y=df['sma_fast'], mode='lines', name=f"SMA({p['fast_period']})", line=dict(color='cyan', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['sma_slow'], mode='lines', name=f"SMA({p['slow_period']})", line=dict(color='magenta', width=1), connectgaps=True), row=1, col=1)
    if p_ind_ui.get('vwap', {}).get('enabled', False) and 'vwap' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['vwap'], mode='lines', name='VWAP', line=dict(color='purple', width=1, dash='dot'), connectgaps=False), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['tenkan_sen'], mode='lines', name='Tenkan', line=dict(color='blue', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['kijun_sen'], mode='lines', name='Kijun', line=dict(color='red', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['chikou_span'], mode='lines', name='Chikou', line=dict(color='#8c564b', width=1.5, dash='dash'), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_a'], mode='lines', name='Senkou A', line=dict(color='rgba(0, 200, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_b'], mode='lines', name='Senkou B', line=dict(color='rgba(200, 0, 0, 0.8)', width=1), connectgaps=True, fill='tonexty', fillcolor='rgba(0,200,0,0.05)'), row=1, col=1)

    # 3-2. サブプロット
    current_row = 2
    for ind_name in active_subplots:
        if ind_name == 'atr':
            fig.add_trace(go.Scatter(x=df.index, y=df['atr'], mode='lines', name='ATR', line=dict(color='#ff7f0e', width=1), connectgaps=True), row=current_row, col=1)
            fig.update_yaxes(title_text="ATR", row=current_row, col=1)
        elif ind_name == 'adx':
            fig.add_trace(go.Scatter(x=df.index, y=df['adx'], mode='lines', name='ADX', line=dict(color='black', width=1.5), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['plus_di'], mode='lines', name='+DI', line=dict(color='green', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['minus_di'], mode='lines', name='-DI', line=dict(color='red', width=1), connectgaps=True), row=current_row, col=1)
            fig.update_yaxes(title_text="ADX", row=current_row, col=1, range=[0, 100])
        elif ind_name == 'rsi':
            fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='#1f77b4', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1); fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)
            fig.update_yaxes(title_text="RSI", row=current_row, col=1, range=[0,100])
        elif ind_name == 'macd':
            colors = ['red' if val > 0 else 'green' for val in df['macd_hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['macd_hist'], name='MACD Hist', marker_color=colors), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd'], mode='lines', name='MACD', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], mode='lines', name='Signal', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
            fig.update_yaxes(title_text="MACD", row=current_row, col=1)
        elif ind_name == 'stoch':
            fig.add_trace(go.Scatter(x=df.index, y=df['stoch_k'], mode='lines', name='%K', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['stoch_d'], mode='lines', name='%D', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1); fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
            fig.update_yaxes(title_text="Stoch", row=current_row, col=1, range=[0,100])
        current_row += 1

    # 3-3. 取引履歴
    symbol_trades = get_trades_for_symbol(symbol)
    if not symbol_trades.empty:
        buy = symbol_trades[symbol_trades['方向'] == 'BUY']; sell = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy['エントリー日時'], y=buy['エントリー価格'],mode='markers', name='Buy',marker=dict(symbol='triangle-up', color='red', size=10)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell['エントリー日時'], y=sell['エントリー価格'],mode='markers', name='Sell', marker=dict(symbol='triangle-down', color='green', size=10)), row=1, col=1)

    # 4. レイアウト更新
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price", legend_title="Indicators", xaxis_rangeslider_visible=False, hovermode='x unified', autosize=True)
    fig.update_yaxes(title_text="Volume", secondary_y=True, row=1, col=1, showticklabels=False)
    if timeframe_name != 'long': fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[15, 9], pattern="hour"), dict(bounds=[11.5, 12.5], pattern="hour")])
    else: fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    
    return pio.to_json(fig)
""",

    "app.py": """from flask import Flask, render_template, jsonify, request
import chart_generator
import logging
import pandas as pd

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

with app.app_context():
    chart_generator.load_data()

@app.route('/')
def index():
    symbols = chart_generator.get_all_symbols(chart_generator.config.DATA_DIR)
    default_params = chart_generator.strategy_params.get('indicators', {})
    return render_template('index.html', symbols=symbols, params=default_params)

@app.route('/get_chart_data')
def get_chart_data():
    try:
        symbol = request.args.get('symbol', type=str)
        timeframe = request.args.get('timeframe', type=str)
        if not symbol or not timeframe:
            return jsonify({"error": "Symbol and timeframe are required"}), 400

        p = chart_generator.strategy_params.get('indicators', {})
        indicator_params = {
            'long_ema_period': request.args.get('long-ema-period', p.get('long_ema_period'), type=int),
            'medium_rsi_period': request.args.get('medium-rsi-period', p.get('medium_rsi_period'), type=int),
            'short_ema_fast': request.args.get('short-ema-fast', p.get('short_ema_fast'), type=int),
            'short_ema_slow': request.args.get('short-ema-slow', p.get('short_ema_slow'), type=int),
            'atr_period': request.args.get('atr-period', p.get('atr_period'), type=int),
            'adx': {'period': request.args.get('adx-period', p.get('adx', {}).get('period'), type=int)},
            'macd': {'fast_period': request.args.get('macd-fast-period', p.get('macd', {}).get('fast_period'), type=int),
                     'slow_period': request.args.get('macd-slow-period', p.get('macd', {}).get('slow_period'), type=int),
                     'signal_period': request.args.get('macd-signal-period', p.get('macd', {}).get('signal_period'), type=int)},
            'stochastic': {'period': request.args.get('stoch-period', p.get('stochastic', {}).get('period'), type=int),
                           'period_dfast': request.args.get('stoch-period-dfast', p.get('stochastic', {}).get('period_dfast'), type=int),
                           'period_dslow': request.args.get('stoch-period-dslow', p.get('stochastic', {}).get('period_dslow'), type=int)},
            'bollinger': {'period': request.args.get('bollinger-period', p.get('bollinger', {}).get('period'), type=int),
                          'devfactor': request.args.get('bollinger-devfactor', p.get('bollinger', {}).get('devfactor'), type=float)},
            'sma': {'fast_period': request.args.get('sma-fast-period', p.get('sma',{}).get('fast_period'), type=int),
                    'slow_period': request.args.get('sma-slow-period', p.get('sma',{}).get('slow_period'), type=int)},
            'vwap': {'enabled': request.args.get('vwap-enabled') == 'true'},
            'ichimoku': {'tenkan_period': request.args.get('ichimoku-tenkan-period', p.get('ichimoku', {}).get('tenkan_period'), type=int),
                         'kijun_period': request.args.get('ichimoku-kijun-period', p.get('ichimoku', {}).get('kijun_period'), type=int),
                         'senkou_span_b_period': request.args.get('ichimoku-senkou-b-period', p.get('ichimoku', {}).get('senkou_span_b_period'), type=int),
                         'chikou_period': request.args.get('ichimoku-chikou-period', p.get('ichimoku', {}).get('chikou_period'), type=int)}
        }

        chart_json = chart_generator.generate_chart_json(symbol, timeframe, indicator_params)
        trades_df = chart_generator.get_trades_for_symbol(symbol)

        trades_df = trades_df.where(pd.notnull(trades_df), None)
        for col in ['損益', '損益(手数料込)']:
            if col in trades_df.columns: trades_df[col] = trades_df[col].round(2)
        trades_json = trades_df.to_json(orient='records')

        return jsonify(chart=chart_json, trades=trades_json)
    except Exception as e:
        app.logger.error(f"Error in /get_chart_data: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
""",

    "templates/index.html": """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Stock Chart</title>
    <style>
        html, body { height: 100%; margin: 0; padding: 0; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f4f4f4; }
        .container { display: flex; flex-direction: column; height: 100%; padding: 15px; box-sizing: border-box; }
        .controls { margin-bottom: 15px; display: flex; flex-wrap: wrap; gap: 10px 15px; align-items: flex-end; flex-shrink: 0; background-color: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .control-group { display: flex; flex-direction: column; }
        .control-group legend { font-weight: bold; font-size: 0.9em; margin-bottom: 5px; color: #333; padding: 0 3px; border-bottom: 2px solid #3498db;}
        .control-group fieldset { border: 1px solid #ccc; border-radius: 4px; padding: 8px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;}
        .input-item { display: flex; flex-direction: column; }
        label { font-weight: bold; font-size: 0.8em; margin-bottom: 4px; color: #555;}
        select, input[type="number"] { padding: 8px; border-radius: 4px; border: 1px solid #ddd; width: 80px; box-sizing: border-box; }
        input[type="checkbox"] { margin-left: 5px; }
        #chart-container { flex-grow: 1; position: relative; min-height: 300px; }
        #chart { width: 100%; height: 100%; }
        .loader { border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 60px; height: 60px; animation: spin 1.5s linear infinite; position: absolute; top: 50%; left: 50%; margin-top: -30px; margin-left: -30px; display: none; z-index: 10; }
        #table-container { flex-shrink: 0; max-height: 30%; overflow: auto; margin-top: 15px; }
        table { border-collapse: collapse; width: 100%; font-size: 0.8em; white-space: nowrap; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #e9ecef; position: sticky; top: 0; z-index: 1; font-weight: 600; }
        tbody tr:hover { background-color: #f5f5f5; cursor: pointer; }
        tbody tr.highlighted { background-color: #fff8dc; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
    <div class="container">
        <h1>Interactive Chart Viewer (v2)</h1>
        <div class="controls">
            <div class="control-group">
                <legend>General</legend>
                <fieldset>
                    <div class="input-item"><label for="symbol-select">銘柄</label><select id="symbol-select">{% for symbol in symbols %}<option value="{{ symbol }}">{{ symbol }}</option>{% endfor %}</select></div>
                    <div class="input-item"><label for="timeframe-select">時間足</label><select id="timeframe-select"><option value="short" selected>短期</option><option value="medium">中期</option><option value="long">長期</option></select></div>
                    <div class="input-item"><label for="vwap-enabled">VWAP</label><input type="checkbox" id="vwap-enabled" {% if params.vwap.enabled %}checked{% endif %}></div>
                </fieldset>
            </div>
            <div class="control-group">
                <legend>MA / BB</legend>
                 <fieldset>
                    <div class="input-item"><label for="sma-fast-period">SMA(速)</label><input type="number" id="sma-fast-period" value="{{ params.sma.fast_period }}"></div>
                    <div class="input-item"><label for="sma-slow-period">SMA(遅)</label><input type="number" id="sma-slow-period" value="{{ params.sma.slow_period }}"></div>
                    <div class="input-item"><label for="short-ema-fast">EMA(速)</label><input type="number" id="short-ema-fast" value="{{ params.short_ema_fast }}"></div>
                    <div class="input-item"><label for="short-ema-slow">EMA(遅)</label><input type="number" id="short-ema-slow" value="{{ params.short_ema_slow }}"></div>
                    <div class="input-item"><label for="long-ema-period">EMA(長)</label><input type="number" id="long-ema-period" value="{{ params.long_ema_period }}"></div>
                    <div class="input-item"><label for="bollinger-period">BB Period</label><input type="number" id="bollinger-period" value="{{ params.bollinger.period }}"></div>
                    <div class="input-item"><label for="bollinger-devfactor">BB StdDev</label><input type="number" id="bollinger-devfactor" step="0.1" value="{{ params.bollinger.devfactor }}"></div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>Oscillators / Volatility</legend>
                 <fieldset>
                    <div class="input-item"><label for="medium-rsi-period">RSI</label><input type="number" id="medium-rsi-period" value="{{ params.medium_rsi_period }}"></div>
                    <div class="input-item"><label for="macd-fast-period">MACD(速)</label><input type="number" id="macd-fast-period" value="{{ params.macd.fast_period }}"></div>
                    <div class="input-item"><label for="macd-slow-period">MACD(遅)</label><input type="number" id="macd-slow-period" value="{{ params.macd.slow_period }}"></div>
                    <div class="input-item"><label for="macd-signal-period">MACD(Sig)</label><input type="number" id="macd-signal-period" value="{{ params.macd.signal_period }}"></div>
                    <div class="input-item"><label for="stoch-period">Stoch %K</label><input type="number" id="stoch-period" value="{{ params.stochastic.period }}"></div>
                    <div class="input-item"><label for="atr-period">ATR</label><input type="number" id="atr-period" value="{{ params.atr_period }}"></div>
                    <div class="input-item"><label for="adx-period">ADX</label><input type="number" id="adx-period" value="{{ params.adx.period }}"></div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>Ichimoku (Short Only)</legend>
                 <fieldset>
                    <div class="input-item"><label for="ichimoku-tenkan-period">Tenkan</label><input type="number" id="ichimoku-tenkan-period" value="{{ params.ichimoku.tenkan_period }}"></div>
                    <div class="input-item"><label for="ichimoku-kijun-period">Kijun</label><input type="number" id="ichimoku-kijun-period" value="{{ params.ichimoku.kijun_period }}"></div>
                    <div class="input-item"><label for="ichimoku-senkou-b-period">Senkou B</label><input type="number" id="ichimoku-senkou-b-period" value="{{ params.ichimoku.senkou_span_b_period }}"></div>
                    <div class="input-item"><label for="ichimoku-chikou-period">Chikou</label><input type="number" id="ichimoku-chikou_period" value="{{ params.ichimoku.chikou_period }}"></div>
                 </fieldset>
            </div>
        </div>
        <div id="chart-container"><div id="loader" class="loader"></div><div id="chart"></div></div>
        <div id="table-container">
             <table id="trades-table">
                <thead><tr>
                    <th>方向</th><th>数量</th><th>エントリー価格</th><th>日時</th><th>根拠</th>
                    <th>決済価格</th><th>日時</th><th>根拠</th><th>損益</th><th>損益(込)</th>
                    <th>SL</th><th>TP</th>
                </tr></thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <script>
        const controls = document.querySelectorAll('.controls select, .controls input');
        const chartDiv = document.getElementById('chart');
        const loader = document.getElementById('loader');
        const tableBody = document.querySelector("#trades-table tbody");

        function formatDateTime(ts) { return ts ? new Date(ts).toLocaleString('ja-JP', { year: '2-digit', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''; }
        function formatNumber(num, digits = 2) { return (num === null || typeof num === 'undefined' || isNaN(num)) ? '' : num.toFixed(digits); }

        function updateChart() {
            loader.style.display = 'block';
            chartDiv.style.opacity = '0.3';

            const params = new URLSearchParams();
            params.append('symbol', document.getElementById('symbol-select').value);
            params.append('timeframe', document.getElementById('timeframe-select').value);
            document.querySelectorAll('.controls input').forEach(input => {
                const key = input.id;
                const value = input.type === 'checkbox' ? input.checked : input.value;
                params.append(key, value);
            });

            fetch(`/get_chart_data?${params.toString()}`)
                .then(response => response.json())
                .then(data => {
                    if(data.error) {
                        console.error('API Error:', data.error);
                        loader.style.display = 'none';
                        chartDiv.style.opacity = '1';
                        return;
                    }
                    const chartJson = data.chart ? JSON.parse(data.chart) : { data: [], layout: {} };
                    const trades = data.trades ? JSON.parse(data.trades) : [];
                    
                    Plotly.newPlot('chart', chartJson.data, chartJson.layout, {responsive: true, scrollZoom: true});
                    buildTradeTable(trades);
                })
                .catch(error => console.error('Error fetching data:', error))
                .finally(() => {
                    loader.style.display = 'none';
                    chartDiv.style.opacity = '1';
                    window.dispatchEvent(new Event('resize'));
                });
        }

        function buildTradeTable(trades) {
            tableBody.innerHTML = '';
            trades.forEach(trade => {
                const row = tableBody.insertRow();
                row.innerHTML = `
                    <td style="color:${trade['方向'] === 'BUY' ? 'red' : 'green'}">${trade['方向']}</td><td>${formatNumber(trade['数量'], 2)}</td>
                    <td>${formatNumber(trade['エントリー価格'])}</td><td>${formatDateTime(trade['エントリー日時'])}</td><td>${trade['エントリー根拠'] || ''}</td>
                    <td>${formatNumber(trade['決済価格'])}</td><td>${formatDateTime(trade['決済日時'])}</td><td>${trade['決済根拠'] || ''}</td>
                    <td style="color:${(trade['損益']||0) >= 0 ? 'blue' : 'red'}">${formatNumber(trade['損益'])}</td>
                    <td style="color:${(trade['損益(手数料込)']||0) >= 0 ? 'blue' : 'red'}">${formatNumber(trade['損益(手数料込)'])}</td>
                    <td>${formatNumber(trade['ストップロス価格'])}</td><td>${formatNumber(trade['テイクプロフィット価格'])}</td>
                `;
                row.addEventListener('click', (event) => {
                    document.querySelectorAll('#trades-table tbody tr').forEach(tr => tr.classList.remove('highlighted'));
                    event.currentTarget.classList.add('highlighted');
                    highlightTradeOnChart(trade);
                });
            });
        }

        function highlightTradeOnChart(trade) {
            const entryTime = trade['エントリー日時'];
            const exitTime = trade['決済日時'];
            if (!entryTime || !exitTime) return;

            const currentLayout = chartDiv.layout;
            const newShapes = (currentLayout.shapes || []).filter(s => s.name !== 'highlight-shape');
            newShapes.push({
                name: 'highlight-shape', type: 'rect', xref: 'x', yref: 'paper',
                x0: entryTime, y0: 0, x1: exitTime, y1: 1,
                fillcolor: 'rgba(255, 255, 0, 0.2)', line: { width: 0 }, layer: 'below'
            });
            Plotly.relayout('chart', { shapes: newShapes });
        }

        window.addEventListener('resize', () => { if(chartDiv.childElementCount > 0) Plotly.Plots.resize(chartDiv); });
        controls.forEach(control => control.addEventListener('change', updateChart));
        document.addEventListener('DOMContentLoaded', updateChart);
    </script>
</body>
</html>
"""
}






# --- ファイル生成処理 ---
def create_files(files_dict):
    for filename, content in files_dict.items():
        # ディレクトリが存在しない場合は作成
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))

        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"ファイルを作成しました: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("プロジェクトファイルの生成を開始します...")
    create_files(project_files)
    print("\nプロジェクトファイルの生成が完了しました。")
    print("\n--- 実行方法 ---")
    print("1. ターミナルで `python create_project_files.py` を実行して、全ファイルを生成します。")
    print("2. `pip install -r requirements.txt` で必要なライブラリをインストールします。")
    print("3. `data`フォルダに、`strategy.yml`の`file_pattern`に一致するCSVデータを配置します。")
    print("4. `strategy.yml` を編集して、データ読み込み方法やトレード戦略を定義します。")
    print("5. `python run_backtrader.py` を実行してバックテストを行います。")
    print("6. `python app.py` を実行してWeb分析ツールを起動し、ブラウザで http://127.0.0.1:5001 を開きます。")