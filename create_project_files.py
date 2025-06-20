# ==============================================================================
# ファイル: create_project_files.py
# 説明: このスクリプトは、戦略ロジックをYAMLファイルで定義できるように改善した
#       株自動トレードシステムの全てのファイルを生成します。
# バージョン: v72.4 (trade_history記録ロジックの修正)
# 主な変更点:
#   - btrader_strategy.py:
#     - executed_sizeをリセットするタイミングを変更し、レポートに正しい数量が
#       記録されるように修正しました。
#   - run_backtrader.py:
#     - TradeListアナライザがストラテジーのexecuted_sizeを正しく参照する
#       ように修正しました。
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
""",

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
INITIAL_CAPITAL = 70000000
BACKTEST_CSV_BASE_TIMEFRAME_STR = 'Minutes'
BACKTEST_CSV_BASE_COMPRESSION = 5
COMMISSION_PERC = 0.0005 # 0.05%
SLIPPAGE_PERC = 0.0002 # 0.02%

# --- ロギング設定 ---
LOG_LEVEL = logging.INFO # INFO or DEBUG
""",

    "strategy.yml": """strategy_name: "ATR Trailing Stop Strategy"
trading_mode:
  long_enabled: True
  short_enabled: True

timeframes:
  long: { timeframe: "Days", compression: 1 }
  medium: { timeframe: "Minutes", compression: 60 }
  short: { timeframe: "Minutes", compression: 5 }

# ==============================================================================
# STRATEGY LOGIC DEFINITION
# ==============================================================================
entry_conditions:
  long: # ロングエントリー条件 (すべてANDで評価)
    - { timeframe: "long", indicator: { name: "ema", params: { period: 20 } }, compare: ">", target: { type: "data", value: "close" } }
    - { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "between", target: { type: "values", value: [0, 100] } }
    - { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 2 } }, indicator2: { name: "ema", params: { period: 5 } } }

  short: # ショートエントリー条件 (すべてANDで評価)
   - { timeframe: "long", indicator: { name: "ema", params: { period: 20 } }, compare: "<", target: { type: "data", value: "close" } }
   - { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "between", target: { type: "values", value: [0, 100] } }
   - { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 2 } }, indicator2: { name: "ema", params: { period: 5 } } }

exit_conditions:
  # take_profitを無効にする場合は、このセクションをコメントアウトするか削除します
  take_profit:
    type: "atr_multiple"
    timeframe: "short"
    params: { period: 14, multiplier: 5.0 }

  stop_loss:
    type: "atr_trailing_stop" # 'atr_multiple' (固定) または 'atr_trailing_stop' (トレーリング)
    timeframe: "short"
    params:
      period: 14
      multiplier: 2.5

sizing:
  risk_per_trade: 0.01 # 1トレードあたりのリスク(資金に対する割合)

# ==============================================================================
# INDICATOR PARAMETERS (for Web UI and Strategy Defaults)
# ==============================================================================
indicators:
  long_ema_period: 200
  medium_rsi_period: 14
  short_ema_fast: 10
  short_ema_slow: 25
  atr_period: 14
  adx:
    period: 14
  macd:
    fast_period: 12
    slow_period: 26
    signal_period: 9
  stochastic:
    period: 14
    period_dfast: 3
    period_dslow: 3
  bollinger:
    period: 20
    devfactor: 2.0
  sma:
    fast_period: 5
    slow_period: 20
  vwap:
    enabled: True
  ichimoku:
    tenkan_period: 9
    kijun_period: 26
    senkou_span_b_period: 52
    chikou_period: 26
""",

    "logger_setup.py": """import logging
import os
from datetime import datetime
import config_backtrader as config

def setup_logging():
    if not os.path.exists(config.LOG_DIR): os.makedirs(config.LOG_DIR)
    log_filename = f"backtest_{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.log"
    log_filepath = os.path.join(config.LOG_DIR, log_filename)
    logging.basicConfig(level=config.LOG_LEVEL,
                        format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
                        handlers=[logging.FileHandler(log_filepath, encoding='utf-8'),
                                  logging.StreamHandler()], force=True)
""",

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

class DynamicStrategy(bt.Strategy):
    params = (('strategy_params', None),)

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.p.strategy_params:
            raise ValueError("戦略パラメータが指定されていません。")

        self.strategy_params = self.p.strategy_params 
        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()
        
        self.entry_order = None
        self.stop_order = None
        self.limit_order = None
        
        self.entry_reason = ""
        self.executed_size = 0
        self.initial_sl_price = 0
        self.final_sl_price = 0
        self.tp_price = 0

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _create_indicators(self):
        indicators = {}
        conditions = self.strategy_params.get('entry_conditions', {})
        exit_conds = self.strategy_params.get('exit_conditions', {})
        unique_defs = {}

        def collect_defs(cond_list):
            for cond in cond_list:
                if 'indicator' in cond: unique_defs[self._get_indicator_key(cond['timeframe'], **cond['indicator'])] = (cond['timeframe'], cond['indicator'])
                if 'indicator1' in cond: unique_defs[self._get_indicator_key(cond['timeframe'], **cond['indicator1'])] = (cond['timeframe'], cond['indicator1'])
                if 'indicator2' in cond: unique_defs[self._get_indicator_key(cond['timeframe'], **cond['indicator2'])] = (cond['timeframe'], cond['indicator2'])
        
        if self.strategy_params.get('trading_mode', {}).get('long_enabled'): collect_defs(conditions.get('long', []))
        if self.strategy_params.get('trading_mode', {}).get('short_enabled'): collect_defs(conditions.get('short', []))
        
        for exit_type in ['take_profit', 'stop_loss']:
            cond = exit_conds.get(exit_type, {})
            if cond.get('type') in ['atr_multiple', 'atr_trailing_stop']:
                atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                key = self._get_indicator_key(cond['timeframe'], 'atr', atr_params)
                unique_defs[key] = (cond['timeframe'], {'name': 'atr', 'params': atr_params})

        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = getattr(bt.indicators, name.capitalize(), getattr(bt.indicators, name.upper(), None))
            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key}")
                indicators[key] = ind_cls(self.data_feeds[timeframe], **params)
            else: self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        def create_cross(cond_list):
            for cond in cond_list:
                if cond.get('type') in ['crossover', 'crossunder']:
                    k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1'])
                    k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    if indicators.get(k1) is not None and indicators.get(k2) is not None:
                        cross_key = f"cross_{k1}_vs_{k2}"
                        if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2])
        
        if self.strategy_params.get('trading_mode', {}).get('long_enabled'): create_cross(conditions.get('long', []))
        if self.strategy_params.get('trading_mode', {}).get('short_enabled'): create_cross(conditions.get('short', []))
        return indicators

    def _evaluate_condition(self, cond):
        tf = cond['timeframe']
        if cond.get('type') in ['crossover', 'crossunder']:
            k1 = self._get_indicator_key(tf, **cond['indicator1'])
            k2 = self._get_indicator_key(tf, **cond['indicator2'])
            cross = self.indicators.get(f"cross_{k1}_vs_{k2}")
            if cross is None: return False
            return cross[0] > 0 if cond['type'] == 'crossover' else cross[0] < 0

        ind = self.indicators.get(self._get_indicator_key(tf, **cond['indicator']))
        if ind is None: return False
        
        tgt, comp, val = cond['target'], cond['compare'], ind[0]
        if tgt['type'] == 'data': tgt_val = getattr(self.data_feeds[tf], tgt['value'])[0]
        else: tgt_val = tgt['value']
            
        if comp == '>': return val > tgt_val
        if comp == '<': return val < tgt_val
        if comp == 'between': return tgt_val[0] < val < tgt_val[1]
        return False

    def _check_all_conditions(self, trade_type):
        conditions = self.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not all(self._evaluate_condition(c) for c in conditions): return False, ""
        return True, " & ".join([_format_condition_reason(c) for c in conditions])

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return

        if order.status == order.Completed:
            self.log(f"{order.getstatusname()}: {'BUY' if order.isbuy() else 'SELL'} Executed, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
            if self.entry_order and self.entry_order.ref == order.ref:
                self.log(f"エントリー成功。ポジションサイズ: {self.position.size}")
                self.executed_size = order.executed.size
                self.entry_order = None
                exit_conds = self.strategy_params.get('exit_conditions', {})
                if self.position.size > 0:
                    if 'take_profit' in exit_conds and exit_conds['take_profit']:
                        self.limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=self.position.size)
                        self.log(f"利確(Limit)注文発注: Price={self.tp_price:.2f}")
                    self.stop_order = self.sell(exectype=bt.Order.Stop, price=self.initial_sl_price, size=self.position.size)
                    self.log(f"損切(Stop)注文発注: Price={self.initial_sl_price:.2f}")
                elif self.position.size < 0:
                    if 'take_profit' in exit_conds and exit_conds['take_profit']:
                        self.limit_order = self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=abs(self.position.size))
                        self.log(f"利確(Limit)注文発注: Price={self.tp_price:.2f}")
                    self.stop_order = self.buy(exectype=bt.Order.Stop, price=self.initial_sl_price, size=abs(self.position.size))
                    self.log(f"損切(Stop)注文発注: Price={self.initial_sl_price:.2f}")

            elif self.stop_order and self.stop_order.ref == order.ref:
                self.log(f"損切り注文約定。")
                if self.limit_order and self.limit_order.alive(): self.broker.cancel(self.limit_order)
                self.stop_order, self.limit_order = None, None
            elif self.limit_order and self.limit_order.ref == order.ref:
                self.log(f"利確注文約定。")
                if self.stop_order and self.stop_order.alive(): self.broker.cancel(self.stop_order)
                self.stop_order, self.limit_order = None, None

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"注文失敗/キャンセル: {order.getstatusname()}")
            if self.entry_order and self.entry_order.ref == order.ref: self.entry_order = None
            elif self.stop_order and self.stop_order.ref == order.ref: self.stop_order = None
            elif self.limit_order and self.limit_order.ref == order.ref: self.limit_order = None

    def notify_trade(self, trade):
        if not trade.isclosed: return
        self.log(f"トレードクローズ, PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")
        self.entry_order = self.stop_order = self.limit_order = None
        # ★★★★★ 修正 ★★★★★
        # ここで executed_size をリセットしない
        # self.executed_size = 0

    def next(self):
        if self.position:
            sl_cond = self.strategy_params.get('exit_conditions', {}).get('stop_loss', {})
            if sl_cond.get('type') == 'atr_trailing_stop' and self.stop_order and self.stop_order.alive():
                atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', {k:v for k,v in sl_cond['params'].items() if k!='multiplier'})
                atr_val = self.indicators.get(atr_key)[0]
                multiplier = sl_cond['params']['multiplier']
                
                new_stop_price = 0
                current_stop = self.stop_order.created.price
                
                if self.position.size > 0:
                    new_stop_price = self.data.close[0] - atr_val * multiplier
                    if new_stop_price > current_stop:
                        self.broker.cancel(self.stop_order)
                        self.stop_order = self.sell(exectype=bt.Order.Stop, price=new_stop_price, size=self.position.size)
                        self.final_sl_price = new_stop_price
                        self.log(f"損切り価格を更新(Long): {current_stop:.2f} -> {new_stop_price:.2f}")
                
                elif self.position.size < 0:
                    new_stop_price = self.data.close[0] + atr_val * multiplier
                    if new_stop_price < current_stop:
                        self.broker.cancel(self.stop_order)
                        self.stop_order = self.buy(exectype=bt.Order.Stop, price=new_stop_price, size=abs(self.position.size))
                        self.final_sl_price = new_stop_price
                        self.log(f"損切り価格を更新(Short): {current_stop:.2f} -> {new_stop_price:.2f}")
            return

        if self.entry_order: return
        
        exit_conds = self.strategy_params.get('exit_conditions', {})
        sl_cond = exit_conds.get('stop_loss', {})
        tp_cond = exit_conds.get('take_profit', {})
        
        atr_key = self._get_indicator_key(sl_cond['timeframe'], 'atr', {k:v for k,v in sl_cond['params'].items() if k!='multiplier'})
        atr_val = self.indicators.get(atr_key)[0]
        if not atr_val or atr_val <= 0: return

        risk_per_share = atr_val * sl_cond['params']['multiplier']
        size = (self.broker.get_cash() * self.strategy_params.get('sizing',{}).get('risk_per_trade',0.01)) / risk_per_share
        entry_price = self.data_feeds['short'].close[0]

        def place_order(trade_type, reason):
            # ★★★★★ 修正 ★★★★★
            # executed_sizeを新規注文発行時にリセット
            self.executed_size = 0
            self.entry_reason = reason
            is_long = trade_type == 'long'
            
            sl_price = entry_price - risk_per_share if is_long else entry_price + risk_per_share
            self.initial_sl_price = self.final_sl_price = sl_price
            
            if tp_cond:
                tp_atr_key = self._get_indicator_key(tp_cond['timeframe'], 'atr', {k:v for k,v in tp_cond['params'].items() if k!='multiplier'})
                tp_atr_val = self.indicators.get(tp_atr_key)[0]
                self.tp_price = entry_price + tp_atr_val * tp_cond['params']['multiplier'] if is_long else entry_price - tp_atr_val * tp_cond['params']['multiplier']
            
            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, SL: {self.initial_sl_price:.2f}, TP: {self.tp_price if tp_cond else 'N/A'}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)

        if self.strategy_params.get('trading_mode', {}).get('long_enabled'):
            met, reason = self._check_all_conditions('long')
            if met: place_order('long', reason)

        if not self.entry_order and self.strategy_params.get('trading_mode', {}).get('short_enabled'):
            met, reason = self._check_all_conditions('short')
            if met: place_order('short', reason)

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        self.logger.info(f'{dt.isoformat()} - {txt}')

def _format_condition_reason(cond):
    tf, type = cond['timeframe'][0].upper(), cond.get('type')
    if type in ['crossover', 'crossunder']:
        i1, i2 = cond['indicator1'], cond['indicator2']
        p1 = ",".join(map(str, i1.get('params', {}).values()))
        p2 = ",".join(map(str, i2.get('params', {}).values()))
        op = "X" if type == 'crossover' else "x"
        return f"{tf}:{i1['name']}({p1}){op}{i2['name']}({p2})"
    ind = cond['indicator']
    p = ",".join(map(str, ind.get('params', {}).values()))
    comp, tgt = cond['compare'], cond['target']
    tgt_val_str = tgt['value'] if tgt['type'] == 'data' else f"({','.join(map(str, tgt['value'])) if isinstance(tgt['value'], list) else tgt['value']})"
    op_str = "in" if comp == "between" else comp
    return f"{tf}:{ind['name']}({p}){op_str}{tgt_val_str}"
""",
    "report_generator.py": """import pandas as pd
import config_backtrader as config
from datetime import datetime

def _format_condition_for_report(cond):
    tf = cond['timeframe'][0].upper()
    cond_type = cond.get('type')
    
    if cond_type == 'crossover' or cond_type == 'crossunder':
        i1 = cond['indicator1']; i2 = cond['indicator2']
        p1 = ",".join(map(str, i1.get('params', {}).values())); p2 = ",".join(map(str, i2.get('params', {}).values()))
        op = " crosses over " if cond_type == 'crossover' else " crosses under "
        return f"{tf}: {i1['name']}({p1}){op}{i2['name']}({p2})"

    ind = cond['indicator']
    p = ",".join(map(str, ind.get('params', {}).values()))
    comp = cond['compare']
    
    tgt = cond['target']
    tgt_val = tgt['value']
    if tgt['type'] == 'values':
        tgt_val = f"{tgt['value'][0]} and {tgt['value'][1]}" if isinstance(tgt['value'], list) and len(tgt['value']) > 1 else str(tgt['value'])
    
    return f"{tf}: {ind['name']}({p}) {comp} {tgt_val}"

def _format_exit_for_report(exit_cond):
    p = exit_cond.get('params', {})
    tf = exit_cond.get('timeframe','?')[0]
    mult = p.get('multiplier')
    period = p.get('period')
    
    if exit_cond.get('type') == 'atr_multiple':
        return f"Fixed ATR(t:{tf}, p:{period}) * {mult}"
    if exit_cond.get('type') == 'atr_trailing_stop':
        return f"Trailing ATR(t:{tf}, p:{period}) * {mult}"
    return "Unknown"

def generate_report(all_results, strategy_params, start_date, end_date):
    total_net_profit = sum(r['pnl_net'] for r in all_results)
    total_gross_won = sum(r['gross_won'] for r in all_results)
    total_gross_lost = sum(r['gross_lost'] for r in all_results)
    total_trades = sum(r['total_trades'] for r in all_results)
    total_win_trades = sum(r['win_trades'] for r in all_results)
    win_rate = (total_win_trades / total_trades) * 100 if total_trades > 0 else 0
    profit_factor = abs(total_gross_won / total_gross_lost) if total_gross_lost != 0 else float('inf')
    avg_profit = total_gross_won / total_win_trades if total_win_trades > 0 else 0
    avg_loss = total_gross_lost / (total_trades - total_win_trades) if (total_trades - total_win_trades) > 0 else 0
    risk_reward_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')

    pnl_eval = "プラス。戦略は利益を生んでいますが、他の指標と合わせて総合的に評価する必要があります。" if total_net_profit > 0 else "マイナス。戦略の見直しが必要です。"
    pf_eval = "良好。安定して利益を出せる可能性が高いです。" if profit_factor > 1.3 else "改善の余地あり。1.0以上が必須です。"
    win_rate_eval = f"{win_rate:.2f}% ({total_win_trades}勝 / {total_trades}トレード)"
    rr_eval = "1.0を上回っており、「利大損小」の傾向が見られます。この数値を維持・向上させることが目標です。" if risk_reward_ratio > 1.0 else "1.0を下回っており、「利小損大」の傾向です。決済ルールの見直しが必要です。"

    p = strategy_params
    
    long_conditions = p.get('entry_conditions', {}).get('long', [])
    short_conditions = p.get('entry_conditions', {}).get('short', [])
    entry_logic_desc = []
    if p.get('trading_mode', {}).get('long_enabled') and long_conditions:
        long_desc = "Long: " + " AND ".join([_format_condition_for_report(c) for c in long_conditions])
        entry_logic_desc.append(long_desc)
    if p.get('trading_mode', {}).get('short_enabled') and short_conditions:
        short_desc = "Short: " + " AND ".join([_format_condition_for_report(c) for c in short_conditions])
        entry_logic_desc.append(short_desc)
    
    entry_signal_desc = " | ".join(entry_logic_desc)
    
    take_profit_desc = _format_exit_for_report(p.get('exit_conditions', {}).get('take_profit', {})) if p.get('exit_conditions', {}).get('take_profit') else "N/A"
    stop_loss_desc = _format_exit_for_report(p.get('exit_conditions', {}).get('stop_loss', {}))

    report_data = {
        '項目': ["分析対象データ日付", "データ期間", "初期資金", "トレード毎のリスク", "手数料率", "スリッページ", "使用戦略", "エントリーロジック", "損切りロジック", "利確ロジック", "---", "純利益", "総利益", "総損失", "プロフィットファクター", "勝率", "総トレード数", "勝ちトレード数", "負けトレード数", "平均利益", "平均損失", "リスクリワードレシオ", "---", "総損益", "プロフィットファクター (PF)", "勝率", "総トレード数", "リスクリワードレシオ"],
        '結果': [datetime.now().strftime('%Y年%m月%d日'), f"{start_date.strftime('%Y年%m月%d日 %H:%M')} 〜 {end_date.strftime('%Y年%m月%d日 %H:%M')}", f"¥{config.INITIAL_CAPITAL:,.0f}", f"{p.get('sizing', {}).get('risk_per_trade', 0):.1%}", f"{config.COMMISSION_PERC:.3%}", f"{config.SLIPPAGE_PERC:.3%}", p.get('strategy_name', 'N/A'), entry_signal_desc, stop_loss_desc, take_profit_desc, "---", f"¥{total_net_profit:,.0f}", f"¥{total_gross_won:,.0f}", f"¥{total_gross_lost:,.0f}", f"{profit_factor:.2f}", f"{win_rate:.2f}%", total_trades, total_win_trades, total_trades - total_win_trades, f"¥{avg_profit:,.0f}", f"¥{avg_loss:,.0f}", f"{risk_reward_ratio:.2f}", "---", f"{total_net_profit:,.0f}円", f"{profit_factor:.2f}", win_rate_eval, f"{total_trades}回", f"{risk_reward_ratio:.2f}"],
        '評価': ["", "", "", "", "", "", "", "", "", "", "---", "", "", "", "", "", "", "", "", "", "", "", "---", pnl_eval, pf_eval, "50%を下回っています。エントリーシグナルの精度向上が課題となります。" if win_rate < 50 else "良好。50%以上を維持することが望ましいです。", "テスト期間に対して十分な取引機会があったか評価してください。", rr_eval]
    }
    return pd.DataFrame(report_data)
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
import btrader_strategy
import notifier
import report_generator

logger = logging.getLogger(__name__)

class TradeList(bt.Analyzer):
    def __init__(self):
        self.trades = []
        self.symbol = "" 

    def start(self):
        self.symbol = self.strategy.data._name

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        entry_price = trade.price
        pnl = trade.pnl
        # ★★★★★ 修正 ★★★★★
        # ストラテジークラスで保持している、最後に約定した数量を参照する
        size = abs(self.strategy.executed_size)
        
        exit_price = 0
        if size > 0:
            if trade.long: exit_price = entry_price + (pnl / size)
            else: exit_price = entry_price - (pnl / size)
        
        exit_reason = "Unknown"
        if trade.isclosed:
            if trade.pnl > 0: exit_reason = "Take Profit"
            elif trade.pnl < 0: exit_reason = "Stop Loss"
            else: exit_reason = "Closed at entry"

        entry_dt_naive = bt.num2date(trade.dtopen).replace(tzinfo=None)
        close_dt_naive = bt.num2date(trade.dtclose).replace(tzinfo=None)

        self.trades.append({
            '銘柄': self.symbol, 
            '方向': 'BUY' if trade.long else 'SELL', 
            '数量': size, 
            'エントリー価格': entry_price, 
            'エントリー日時': entry_dt_naive.isoformat(), 
            'エントリー根拠': self.strategy.entry_reason, 
            '決済価格': exit_price,
            '決済日時': close_dt_naive.isoformat(), 
            '決済根拠': exit_reason, 
            '損益': trade.pnl, 
            '損益(手数料込)': trade.pnlcomm, 
            'ストップロス価格': self.strategy.final_sl_price, 
            'テイクプロフィット価格': self.strategy.tp_price
        })

    def get_analysis(self):
        return self.trades

def get_csv_files(data_dir):
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    return glob.glob(file_pattern)

def run_backtest_for_symbol(filepath, strategy_cls, strategy_params):
    symbol = os.path.basename(filepath).split('_')[0]
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(strategy_cls, strategy_params=strategy_params)
    try:
        dataframe = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        dataframe.columns = [x.lower() for x in dataframe.columns]
    except Exception as e:
        logger.error(f"CSVファイルの読み込みに失敗しました: {filepath} - {e}")
        return None, None, None, None
    
    data = bt.feeds.PandasData(dataname=dataframe, timeframe=bt.TimeFrame.TFrame(config.BACKTEST_CSV_BASE_TIMEFRAME_STR), compression=config.BACKTEST_CSV_BASE_COMPRESSION)
    data._name = symbol
    cerebro.adddata(data)

    tf_medium = strategy_params['timeframes']['medium']
    cerebro.resampledata(data, timeframe=bt.TimeFrame.TFrame(tf_medium['timeframe']), compression=tf_medium['compression'], name="medium")
    tf_long = strategy_params['timeframes']['long']
    cerebro.resampledata(data, timeframe=bt.TimeFrame.TFrame(tf_long['timeframe']), compression=tf_long['compression'], name="long")
    
    cerebro.broker.set_cash(config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=config.COMMISSION_PERC)
    cerebro.broker.set_slippage_perc(perc=config.SLIPPAGE_PERC)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addanalyzer(TradeList, _name='tradelist')
    
    results = cerebro.run()
    strat = results[0]
    trade_analysis = strat.analyzers.trade.get_analysis()
    trade_list = strat.analyzers.tradelist.get_analysis()
    
    raw_stats = {'symbol': symbol, 'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0), 'gross_won': trade_analysis.get('won', {}).get('pnl', {}).get('total', 0), 'gross_lost': trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0), 'total_trades': trade_analysis.get('total', {}).get('total', 0), 'win_trades': trade_analysis.get('won', {}).get('total', 0)}
    return raw_stats, dataframe.index[0], dataframe.index[-1], trade_list

def main():
    logger_setup.setup_logging()
    logger.info("--- 全銘柄バックテスト開始 ---")
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path): os.makedirs(dir_path)
    with open('strategy.yml', 'r', encoding='utf-8') as f:
        strategy_params = yaml.safe_load(f)
    
    csv_files = get_csv_files(config.DATA_DIR)
    if not csv_files:
        logger.error(f"{config.DATA_DIR} に指定された形式のCSVデータが見つかりません。")
        return
        
    all_results, all_trades, all_details, start_dates, end_dates = [], [], [], [], []
    for filepath in csv_files:
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(filepath, btrader_strategy.DynamicStrategy, strategy_params)
        if stats:
            all_results.append(stats)
            all_trades.extend(trade_list)
            if start_date is not None and pd.notna(start_date): start_dates.append(start_date)
            if end_date is not None and pd.notna(end_date): end_dates.append(end_date)
            total_trades, win_trades = stats['total_trades'], stats['win_trades']
            gross_won, gross_lost = stats['gross_won'], stats['gross_lost']
            win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
            profit_factor = abs(gross_won / gross_lost) if gross_lost != 0 else float('inf')
            avg_profit = gross_won / win_trades if win_trades > 0 else 0
            avg_loss = gross_lost / (total_trades - win_trades) if (total_trades - win_trades) > 0 else 0
            risk_reward_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')
            all_details.append({"銘柄": stats['symbol'], "純利益": f"¥{stats['pnl_net']:,.2f}", "総利益": f"¥{gross_won:,.2f}", "総損失": f"¥{gross_lost:,.2f}", "プロフィットファクター": f"{profit_factor:.2f}", "勝率": f"{win_rate:.2f}%", "総トレード数": total_trades, "勝ちトレード数": win_trades, "負けトレード数": total_trades - win_trades, "平均利益": f"¥{avg_profit:,.2f}", "平均損失": f"¥{avg_loss:,.2f}", "リスクリワードレシオ": f"{risk_reward_ratio:.2f}"})

    if not all_results:
        logger.warning("有効なバックテスト結果がありませんでした。")
        return
    if not start_dates or not end_dates:
        logger.warning("有効なデータ期間が取得できなかったため、レポート生成をスキップします。")
        return

    overall_start, overall_end = min(start_dates), max(end_dates)
    report_df = report_generator.generate_report(all_results, strategy_params, overall_start, overall_end)
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')

    summary_path = os.path.join(config.REPORT_DIR, f"summary_{timestamp}.csv")
    report_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    logger.info(f"サマリーレポートを保存しました: {summary_path}")

    if all_details:
        detail_df = pd.DataFrame(all_details).set_index('銘柄')
        detail_path = os.path.join(config.REPORT_DIR, f"detail_{timestamp}.csv")
        detail_df.to_csv(detail_path, encoding='utf-8-sig')
        logger.info(f"銘柄別詳細レポートを保存しました: {detail_path}")
    if all_trades:
        trades_df = pd.DataFrame(all_trades)
        trades_path = os.path.join(config.REPORT_DIR, f"trade_history_{timestamp}.csv")
        trades_df.to_csv(trades_path, index=False, encoding='utf-8-sig')
        logger.info(f"統合取引履歴を保存しました: {trades_path}")

    logger.info("\\n\\n★★★ 全銘柄バックテストサマリー ★★★\\n" + report_df.to_string())
    notifier.send_email(subject="【Backtrader】全銘柄バックテスト完了レポート", body=f"全てのバックテストが完了しました。\\n\\n--- サマリー ---\\n{report_df.to_string()}")

if __name__ == '__main__':
    main()
""",
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
    global trade_history_df, strategy_params
    
    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    if trade_history_path:
        trade_history_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
        logger.info(f"取引履歴ファイルを読み込みました: {trade_history_path}")
    else:
        trade_history_df = pd.DataFrame()
        logger.warning("取引履歴レポートが見つかりません。チャートに取引は表示されません。")

    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("strategy.yml が見つかりません。")
        strategy_params = {}

    all_symbols = get_all_symbols(config.DATA_DIR)
    for symbol in all_symbols:
        csv_pattern = os.path.join(config.DATA_DIR, f"{symbol}*.csv")
        data_files = glob.glob(csv_pattern)
        if data_files:
            df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
            df.columns = [x.lower() for x in df.columns]
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            price_data_cache[symbol] = df
    logger.info(f"{len(price_data_cache)} 件の銘柄データをキャッシュしました。")

def find_latest_report(report_dir, prefix):
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_all_symbols(data_dir):
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    files = glob.glob(file_pattern)
    return sorted(list(set(os.path.basename(f).split('_')[0] for f in files)))

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
    if symbol not in price_data_cache: return {}
    base_df = price_data_cache[symbol]
    symbol_trades = get_trades_for_symbol(symbol)
    
    p_ind_ui = indicator_params
    p_tf_def = strategy_params['timeframes']
    p_filter_def = strategy_params.get('filters', {})

    df, title = None, ""
    sub_plots = defaultdict(lambda: False)

    if timeframe_name == 'short':
        df = base_df.copy()
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
        df = add_ichimoku(df, p_ind_ui['ichimoku']); sub_plots['ichimoku'] = True
        if p_ind_ui.get('vwap', {}).get('enabled', False): df = add_vwap(df); sub_plots['vwap'] = True
        title = f"{symbol} Short-Term ({p_tf_def['short']['compression']}min)"
    elif timeframe_name == 'medium':
        df = resample_ohlc(base_df, f"{p_tf_def['medium']['compression']}min")
        p = p_ind_ui['medium_rsi_period']
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=p).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
        rs = gain / loss.replace(0, 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs)); sub_plots['rsi'] = True
        if p_ind_ui.get('vwap', {}).get('enabled', False): df = add_vwap(df); sub_plots['vwap'] = True
        title = f"{symbol} Medium-Term ({p_tf_def['medium']['compression']}min)"
    elif timeframe_name == 'long':
        df = resample_ohlc(base_df, 'D')
        title = f'{symbol} Long-Term (Daily)'

    if df is None or df.empty: return {}
    
    df = add_adx(df, p_ind_ui['adx']['period']); sub_plots['adx'] = True
    df = add_atr(df, p_ind_ui['atr_period']); sub_plots['atr'] = True
    p = p_ind_ui['sma']
    df['sma_fast'] = df['close'].rolling(window=p['fast_period']).mean()
    df['sma_slow'] = df['close'].rolling(window=p['slow_period']).mean()
    p = p_ind_ui['bollinger']
    df['bb_middle'] = df['close'].rolling(window=p['period']).mean()
    df['bb_std'] = df['close'].rolling(window=p['period']).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * p['devfactor'])
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * p['devfactor'])
    df['ema_fast'] = df['close'].ewm(span=p_ind_ui['short_ema_fast'], adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=p_ind_ui['short_ema_slow'], adjust=False).mean()
    df['ema_long'] = df['close'].ewm(span=p_ind_ui['long_ema_period'], adjust=False).mean()

    active_subplots = [k for k, v in sub_plots.items() if v and k in ['atr', 'adx', 'rsi', 'macd', 'stoch']]
    rows = 1 + len(active_subplots)
    specs = [[{"secondary_y": True}]] + [[{'secondary_y': False}] for _ in active_subplots]
    main_height = max(0.4, 1.0 - (0.15 * len(active_subplots)))
    sub_height = (1 - main_height) / len(active_subplots) if active_subplots else 0
    row_heights = [main_height] + [sub_height] * len(active_subplots) if active_subplots else [1]
    
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, specs=specs, row_heights=row_heights)
    
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker=dict(color=volume_colors, opacity=0.3)), secondary_y=True, row=1, col=1)

    p = p_ind_ui['bollinger']; fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, fillcolor='rgba(128,128,128,0.1)', fill='tonexty', hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], mode='lines', name=f"BB({p['period']},{p['devfactor']})", line=dict(color='gray', width=0.7, dash='dash'), connectgaps=True), row=1, col=1)
    p = p_ind_ui['sma']; fig.add_trace(go.Scatter(x=df.index, y=df['sma_fast'], mode='lines', name=f"SMA({p['fast_period']})", line=dict(color='cyan', width=1), connectgaps=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['sma_slow'], mode='lines', name=f"SMA({p['slow_period']})", line=dict(color='magenta', width=1), connectgaps=True), row=1, col=1)
    if sub_plots['vwap']: fig.add_trace(go.Scatter(x=df.index, y=df['vwap'], mode='lines', name='VWAP', line=dict(color='purple', width=1, dash='dot'), connectgaps=False), row=1, col=1)
    if sub_plots['ichimoku']:
        fig.add_trace(go.Scatter(x=df.index, y=df['tenkan_sen'], mode='lines', name='Tenkan', line=dict(color='blue', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['kijun_sen'], mode='lines', name='Kijun', line=dict(color='red', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['chikou_span'], mode='lines', name='Chikou', line=dict(color='#8c564b', width=1.5, dash='dash'), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_a'], mode='lines', name='Senkou A', line=dict(color='rgba(0, 200, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_b'], mode='lines', name='Senkou B', line=dict(color='rgba(200, 0, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)

    current_row = 2
    if sub_plots['atr']:
        fig.add_trace(go.Scatter(x=df.index, y=df['atr'], mode='lines', name='ATR', line=dict(color='#ff7f0e', width=1), connectgaps=True), row=current_row, col=1); fig.update_yaxes(title_text="ATR", row=current_row, col=1); current_row += 1
    if sub_plots['adx']:
        fig.add_trace(go.Scatter(x=df.index, y=df['adx'], mode='lines', name='ADX', line=dict(color='black', width=1.5), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['plus_di'], mode='lines', name='+DI', line=dict(color='green', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['minus_di'], mode='lines', name='-DI', line=dict(color='red', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="ADX", row=current_row, col=1, range=[0, 100]); current_row += 1
    if sub_plots['rsi']:
        rsi_upper = p_filter_def.get('medium_rsi_upper', 70)
        rsi_lower = p_filter_def.get('medium_rsi_lower', 30)
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='#1f77b4', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=rsi_upper, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=rsi_lower, line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="RSI", row=current_row, col=1, range=[0,100]); current_row += 1
    if sub_plots['macd']:
        colors = ['red' if val > 0 else 'green' for val in df['macd_hist']]
        fig.add_trace(go.Bar(x=df.index, y=df['macd_hist'], name='MACD Hist', marker_color=colors), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd'], mode='lines', name='MACD', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], mode='lines', name='Signal', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="MACD", row=current_row, col=1); current_row += 1
    if sub_plots['stoch']:
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_k'], mode='lines', name='%K', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_d'], mode='lines', name='%D', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="Stoch", row=current_row, col=1, range=[0,100]); current_row += 1

    if not symbol_trades.empty:
        buy = symbol_trades[symbol_trades['方向'] == 'BUY']; sell = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy['エントリー日時'], y=buy['エントリー価格'],mode='markers', name='Buy',marker=dict(symbol='triangle-up', color='red', size=10)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell['エントリー日時'], y=sell['エントリー価格'],mode='markers', name='Sell', marker=dict(symbol='triangle-down', color='green', size=10)), row=1, col=1)
        for _, trade in symbol_trades.iterrows():
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['テイクプロフィット価格'],x1=trade['決済日時'], y1=trade['テイクプロフィット価格'],line=dict(color="red", width=2, dash="dash"),row=1, col=1)
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['ストップロス価格'],x1=trade['決済日時'], y1=trade['ストップロス価格'],line=dict(color="green", width=2, dash="dash"),row=1, col=1)

    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price", legend_title="Indicators", xaxis_rangeslider_visible=False, hovermode='x unified', autosize=True)
    fig.update_yaxes(title_text="Volume", secondary_y=True, row=1, col=1)
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
            'long_ema_period': request.args.get('long_ema_period', p.get('long_ema_period'), type=int),
            'medium_rsi_period': request.args.get('medium_rsi_period', p.get('medium_rsi_period'), type=int),
            'short_ema_fast': request.args.get('short_ema_fast', p.get('short_ema_fast'), type=int),
            'short_ema_slow': request.args.get('short_ema_slow', p.get('short_ema_slow'), type=int),
            'atr_period': request.args.get('atr_period', p.get('atr_period'), type=int),
            'adx': {'period': request.args.get('adx_period', p.get('adx', {}).get('period'), type=int)},
            'macd': {'fast_period': request.args.get('macd_fast_period', p.get('macd', {}).get('fast_period'), type=int),
                     'slow_period': request.args.get('macd_slow_period', p.get('macd', {}).get('slow_period'), type=int),
                     'signal_period': request.args.get('macd_signal_period', p.get('macd', {}).get('signal_period'), type=int)},
            'stochastic': {'period': request.args.get('stoch_period', p.get('stochastic', {}).get('period'), type=int),
                           'period_dfast': request.args.get('stoch_period_dfast', p.get('stochastic', {}).get('period_dfast'), type=int),
                           'period_dslow': request.args.get('stoch_period_dslow', p.get('stochastic', {}).get('period_dslow'), type=int)},
            'bollinger': {'period': request.args.get('bollinger_period', p.get('bollinger', {}).get('period'), type=int),
                          'devfactor': request.args.get('bollinger_devfactor', p.get('bollinger', {}).get('devfactor'), type=float)},
            'sma': {'fast_period': request.args.get('sma_fast_period', p.get('sma',{}).get('fast_period'), type=int),
                    'slow_period': request.args.get('sma_slow_period', p.get('sma',{}).get('slow_period'), type=int)},
            'vwap': {'enabled': request.args.get('vwap_enabled') == 'true'},
            'ichimoku': {'tenkan_period': request.args.get('ichimoku_tenkan_period', p.get('ichimoku', {}).get('tenkan_period'), type=int),
                         'kijun_period': request.args.get('ichimoku_kijun_period', p.get('ichimoku', {}).get('kijun_period'), type=int),
                         'senkou_span_b_period': request.args.get('ichimoku_senkou_b_period', p.get('ichimoku', {}).get('senkou_span_b_period'), type=int),
                         'chikou_period': request.args.get('ichimoku_chikou_period', p.get('ichimoku', {}).get('chikou_period'), type=int)}
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
            
            const params = {
                symbol: document.getElementById('symbol-select').value,
                timeframe: document.getElementById('timeframe-select').value,
                vwap_enabled: document.getElementById('vwap-enabled').checked,
                ...Array.from(document.querySelectorAll('input[type="number"]')).reduce((obj, input) => {
                    obj[input.id.replace(/-/g, '_')] = input.value;
                    return obj;
                }, {})
            };
            
            fetch(`/get_chart_data?${new URLSearchParams(params).toString()}`)
                .then(response => response.json())
                .then(data => {
                    if(data.error) {
                        console.error('API Error:', data.error);
                        return;
                    }
                    const chartJson = JSON.parse(data.chart);
                    const trades = JSON.parse(data.trades);
                    if (chartJson.data && chartJson.layout) {
                        Plotly.newPlot('chart', chartJson.data, chartJson.layout, {responsive: true, scrollZoom: true});
                    }
                    if (trades) buildTradeTable(trades);
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
""",
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
    print("プロジェクトファイルの生成を開始します (v71.6)...")
    create_files(project_files)
    print("\nプロジェクトファイルの生成が完了しました。")
    print("\n--- 実行方法 ---")
    print("1. ターミナルで `python create_project_files.py` を実行して、全ファイルを生成します。")
    print("2. `pip install -r requirements.txt` で必要なライブラリをインストールします。")
    print("3. `data`フォルダに必要なCSVデータを配置します。")
    print("4. `strategy.yml` を編集して、好みのトレード戦略を定義します。")
    print("5. `python run_backtrader.py` を実行してバックテストを行います（分析前に必須）。")
    print("6. `python app.py` を実行してWeb分析ツールを起動します。")
    print("7. Webブラウザで http://127.0.0.1:5001 を開きます")
