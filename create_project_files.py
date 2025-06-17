# ==============================================================================
# ファイル: create_project_files.py
# 説明: このスクリプトは、チャート生成機能を強化した株自動トレードシステムの
#       全てのファイルを生成します。
# 変更点 (v52):
#   - templates/index.html:
#     - ページが空白で表示される問題を修正（HTML構造の復元）。
#     - カスタムツールチップ関連のコードを完全に削除。
#   - chart_generator.py:
#     - Plotly標準のツールチップ表示に戻すため、hovermodeを'x unified'に変更し、
#       各トレースのhoverinfo='none'を削除。
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

    "strategy.yml": """strategy_name: "Long/Short Multi-Timeframe Strategy"
trading_mode:
  long_enabled: True
  short_enabled: True
timeframes:
  long: {timeframe: "Days", compression: 1}
  medium: {timeframe: "Minutes", compression: 60}
  short: {timeframe: "Minutes", compression: 5}
indicators:
  long_ema_period: 200
  medium_rsi_period: 14
  short_ema_fast: 10
  short_ema_slow: 25
  atr_period: 14
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
filters:
  medium_rsi_lower: 30
  medium_rsi_upper: 70
exit_rules:
  take_profit_atr_multiplier: 2.0
  stop_loss_atr_multiplier: 1.0
sizing:
  risk_per_trade: 0.005 # 1トレードあたりのリスク(資金に対する割合)
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
    "btrader_strategy.py": """import backtrader as bt, yaml, logging

class MultiTimeFrameStrategy(bt.Strategy):
    params = (('strategy_file', 'strategy.yml'),)

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        with open(self.p.strategy_file, 'r', encoding='utf-8') as f:
            self.strategy_params = yaml.safe_load(f)

        p = self.strategy_params
        p_ind = p['indicators']
        p_macd = p_ind.get('macd', {})
        p_stoch = p_ind.get('stochastic', {})

        self.short_data, self.medium_data, self.long_data = self.datas[0], self.datas[1], self.datas[2]
        self.long_ema = bt.indicators.EMA(self.long_data.close, period=p_ind['long_ema_period'])
        self.medium_rsi = bt.indicators.RSI(self.medium_data.close, period=p_ind['medium_rsi_period'])
        self.short_ema_fast = bt.indicators.EMA(self.short_data.close, period=p_ind['short_ema_fast'])
        self.short_ema_slow = bt.indicators.EMA(self.short_data.close, period=p_ind['short_ema_slow'])
        self.short_cross = bt.indicators.CrossOver(self.short_ema_fast, self.short_ema_slow)
        self.atr = bt.indicators.ATR(self.short_data, period=p_ind['atr_period'])
        self.macd = bt.indicators.MACD(self.short_data.close,
                                       period_me1=p_macd.get('fast_period', 12),
                                       period_me2=p_macd.get('slow_period', 26),
                                       period_signal=p_macd.get('signal_period', 9))
        self.stochastic = bt.indicators.StochasticSlow(self.short_data,
                                                        period=p_stoch.get('period', 14),
                                                        period_dfast=p_stoch.get('period_dfast', 3),
                                                        period_dslow=p_stoch.get('period_dslow', 3))
        self.order = None
        self.trade_size = 0
        self.entry_reason = None
        self.sl_price = 0
        self.tp_price = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        if order.status == order.Completed:
            if order.isbuy(): self.log(f"BUY EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
            elif order.issell(): self.log(f"SELL EXECUTED, Price: {order.executed.price:.2f}, Size: {order.executed.size:.2f}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]: self.log(f"Order {order.getstatusname()}")
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            self.trade_size = trade.size
            return
        self.log(f"OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}")

    def next(self):
        if self.order or self.position: return

        p = self.strategy_params
        filters = p['filters']
        exit_rules = p['exit_rules']
        sizing_params = p['sizing']
        trading_mode = p.get('trading_mode', {'long_enabled': True, 'short_enabled': False})

        atr_val = self.atr[0]
        if atr_val == 0: return

        # --- 買い戦略の条件 ---
        if trading_mode.get('long_enabled', True):
            long_ok = self.long_data.close[0] > self.long_ema[0]
            medium_ok = filters['medium_rsi_lower'] < self.medium_rsi[0] < filters['medium_rsi_upper']
            short_ok = self.short_cross[0] > 0

            if long_ok and medium_ok and short_ok:
                self.sl_price = self.short_data.close[0] - atr_val * exit_rules['stop_loss_atr_multiplier']
                self.tp_price = self.short_data.close[0] + atr_val * exit_rules['take_profit_atr_multiplier']

                risk_per_share = atr_val * exit_rules['stop_loss_atr_multiplier']
                allowed_risk_amount = self.broker.get_cash() * sizing_params['risk_per_trade']
                size = allowed_risk_amount / risk_per_share if risk_per_share > 0 else 0

                self.entry_reason = f"L:C>EMA, M:RSI OK, S:GoldenCross"
                self.log(f"BUY CREATE, Price: {self.short_data.close[0]:.2f}, Size: {size:.2f}")
                self.order = self.buy_bracket(size=size, price=self.short_data.close[0], limitprice=self.tp_price, stopprice=self.sl_price)
                return

        # --- 売り戦略の条件 ---
        if trading_mode.get('short_enabled', True):
            long_sell_ok = self.long_data.close[0] < self.long_ema[0]
            medium_sell_ok = filters['medium_rsi_lower'] < self.medium_rsi[0] < filters['medium_rsi_upper']
            short_sell_ok = self.short_cross[0] < 0

            if long_sell_ok and medium_sell_ok and short_sell_ok:
                self.sl_price = self.short_data.close[0] + atr_val * exit_rules['stop_loss_atr_multiplier']
                self.tp_price = self.short_data.close[0] - atr_val * exit_rules['take_profit_atr_multiplier']

                risk_per_share = atr_val * exit_rules['stop_loss_atr_multiplier']
                allowed_risk_amount = self.broker.get_cash() * sizing_params['risk_per_trade']
                size = allowed_risk_amount / risk_per_share if risk_per_share > 0 else 0

                self.entry_reason = f"L:C<EMA, M:RSI OK, S:DeadCross"
                self.log(f"SELL CREATE, Price: {self.short_data.close[0]:.2f}, Size: {size:.2f}")
                self.order = self.sell_bracket(size=size, price=self.short_data.close[0], limitprice=self.tp_price, stopprice=self.sl_price)

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        self.logger.info(f'{dt.isoformat()} - {txt}')
""",

    "report_generator.py": """import pandas as pd
import config_backtrader as config
from datetime import datetime

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

    def format_tf(tf_dict):
        unit_map = {"Minutes": "分", "Days": "日", "Hours": "時間", "Weeks": "週"}
        unit = unit_map.get(tf_dict['timeframe'], tf_dict['timeframe'])
        return f"{tf_dict['compression']}{unit}足"

    timeframe_desc = f"{format_tf(p['timeframes']['short'])}（短期）、{format_tf(p['timeframes']['medium'])}（中期）、{format_tf(p['timeframes']['long'])}（長期）"

    trading_mode = p.get('trading_mode', {})
    long_enabled = trading_mode.get('long_enabled', True)
    short_enabled = trading_mode.get('short_enabled', False)

    if long_enabled and not short_enabled:
        env_logic_desc = f"Long Only: 長期足({format_tf(p['timeframes']['long'])})の終値 > EMA({p['indicators']['long_ema_period']})"
    elif not long_enabled and short_enabled:
        env_logic_desc = f"Short Only: 長期足({format_tf(p['timeframes']['long'])})の終値 < EMA({p['indicators']['long_ema_period']})"
    else:
        env_logic_desc = f"Long/Short: 長期トレンドに順張り"

    entry_signal_desc = f"短期足EMA({p['indicators']['short_ema_fast']})とEMA({p['indicators']['short_ema_slow']})のクロス & 中期足RSI({p['indicators']['medium_rsi_period']})が{p['filters']['medium_rsi_lower']}~{p['filters']['medium_rsi_upper']}の範囲"
    stop_loss_desc = f"ATRトレーリング (期間: {p['indicators']['atr_period']}, 倍率: {p['exit_rules']['stop_loss_atr_multiplier']}x)"
    take_profit_desc = f"ATRトレーリング (期間: {p['indicators']['atr_period']}, 倍率: {p['exit_rules']['take_profit_atr_multiplier']}x)"

    report_data = {
        '項目': ["分析対象データ日付", "データ期間", "初期資金", "トレード毎のリスク", "手数料率", "スリッページ",
                 "使用戦略", "足種", "環境認識ロジック", "有効なエントリーシグナル", "有効な損切りシグナル", "有効な利確シグナル",
                 "---", "純利益", "総利益", "総損失", "プロフィットファクター", "勝率", "総トレード数",
                 "勝ちトレード数", "負けトレード数", "平均利益", "平均損失", "リスクリワードレシオ",
                 "---", "総損益", "プロフィットファクター (PF)", "勝率", "総トレード数", "リスクリワードレシオ"],
        '結果': [datetime.now().strftime('%Y年%m月%d日'),
                 f"{start_date.strftime('%Y年%m月%d日 %H:%M')} 〜 {end_date.strftime('%Y年%m月%d日 %H:%M')}",
                 f"¥{config.INITIAL_CAPITAL:,.0f}", f"{p['sizing']['risk_per_trade']:.1%}",
                 f"{config.COMMISSION_PERC:.3%}", f"{config.SLIPPAGE_PERC:.3%}",
                 p['strategy_name'], timeframe_desc, env_logic_desc, entry_signal_desc, stop_loss_desc, take_profit_desc,
                 "---", f"¥{total_net_profit:,.0f}", f"¥{total_gross_won:,.0f}", f"¥{total_gross_lost:,.0f}",
                 f"{profit_factor:.2f}", f"{win_rate:.2f}%", total_trades, total_win_trades,
                 total_trades - total_win_trades, f"¥{avg_profit:,.0f}", f"¥{avg_loss:,.0f}",
                 f"{risk_reward_ratio:.2f}", "---", f"{total_net_profit:,.0f}円", f"{profit_factor:.2f}",
                 win_rate_eval, f"{total_trades}回", f"{risk_reward_ratio:.2f}"],
        '評価': ["", "", "", "", "", "", "", "", "", "", "", "", "---", "", "", "", "", "", "", "", "", "", "", "", "---",
                 pnl_eval, pf_eval, "50%を下回っています。エントリーシグナルの精度向上が課題となります。" if win_rate < 50 else "良好。50%以上を維持することが望ましいです。",
                 "テスト期間に対して十分な取引機会があったか評価してください。", rr_eval]
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
        self.symbol = self.strategy.data._name
        self.entry_info = {}

    def notify_trade(self, trade):
        if trade.isopen:
            self.entry_info[trade.ref] = {
                'size': trade.size,
                'entry_reason': self.strategy.entry_reason,
                'stop_loss_price': self.strategy.sl_price,
                'take_profit_price': self.strategy.tp_price,
                'long_ema': self.strategy.long_ema[0],
                'medium_rsi': self.strategy.medium_rsi[0]
            }
            return

        if trade.isclosed:
            p = self.strategy.strategy_params
            exit_rules = p['exit_rules']

            if trade.pnl >= 0:
                exit_reason = f"Take Profit (ATR x{exit_rules['take_profit_atr_multiplier']})"
            else:
                exit_reason = f"Stop Loss (ATR x{exit_rules['stop_loss_atr_multiplier']})"

            info = self.entry_info.pop(trade.ref, {})
            original_size = info.get('size', 0)

            entry_dt_naive = bt.num2date(trade.dtopen).replace(tzinfo=None)
            close_dt_naive = bt.num2date(trade.dtclose).replace(tzinfo=None)

            exit_price = 0
            if original_size:
                 exit_price = trade.price + (trade.pnl / original_size)

            self.trades.append({
                '銘柄': self.symbol,
                '方向': 'BUY' if trade.long else 'SELL',
                '数量': original_size,
                'エントリー価格': trade.price,
                'エントリー日時': entry_dt_naive.isoformat(),
                'エントリー根拠': info.get('entry_reason', "N/A"),
                '決済価格': exit_price,
                '決済日時': close_dt_naive.isoformat(),
                '決済根拠': exit_reason,
                '損益': trade.pnl,
                '損益(手数料込)': trade.pnlcomm,
                'ストップロス価格': info.get('stop_loss_price', 0),
                'テイクプロフィット価格': info.get('take_profit_price', 0),
                'エントリー時長期EMA': info.get('long_ema', 0),
                'エントリー時中期RSI': info.get('medium_rsi', 0)
            })

    def get_analysis(self):
        return self.trades

def get_csv_files(data_dir):
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    return glob.glob(file_pattern)

def run_backtest_for_symbol(filepath, strategy_cls):
    symbol = os.path.basename(filepath).split('_')[0]
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(strategy_cls)

    try:
        dataframe = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        dataframe.columns = [x.lower() for x in dataframe.columns]
    except Exception as e:
        logger.error(f"CSVファイルの読み込みに失敗しました: {filepath} - {e}")
        return None, None, None, None

    data = bt.feeds.PandasData(dataname=dataframe, timeframe=bt.TimeFrame.TFrame(config.BACKTEST_CSV_BASE_TIMEFRAME_STR), compression=config.BACKTEST_CSV_BASE_COMPRESSION)
    data._name = symbol
    cerebro.adddata(data)

    with open('strategy.yml', 'r', encoding='utf-8') as f:
        strategy_params = yaml.safe_load(f)

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

    raw_stats = {
        'symbol': symbol,
        'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0),
        'gross_won': trade_analysis.get('won', {}).get('pnl', {}).get('total', 0),
        'gross_lost': trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0),
        'total_trades': trade_analysis.get('total', {}).get('total', 0),
        'win_trades': trade_analysis.get('won', {}).get('total', 0),
    }
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

    all_results = []
    all_trades = []
    all_details = []
    start_dates, end_dates = [], []
    for filepath in csv_files:
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(filepath, btrader_strategy.MultiTimeFrameStrategy)
        if stats:
            all_results.append(stats)
            all_trades.extend(trade_list)
            if start_date is not None and pd.notna(start_date): start_dates.append(start_date)
            if end_date is not None and pd.notna(end_date): end_dates.append(end_date)

            total_trades = stats['total_trades']
            win_trades = stats['win_trades']
            gross_won = stats['gross_won']
            gross_lost = stats['gross_lost']
            win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
            profit_factor = abs(gross_won / gross_lost) if gross_lost != 0 else float('inf')
            avg_profit = gross_won / win_trades if win_trades > 0 else 0
            avg_loss = gross_lost / (total_trades - win_trades) if (total_trades - win_trades) > 0 else 0
            risk_reward_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')

            all_details.append({
                "銘柄": stats['symbol'],
                "純利益": f"¥{stats['pnl_net']:,.2f}",
                "総利益": f"¥{gross_won:,.2f}",
                "総損失": f"¥{gross_lost:,.2f}",
                "プロフィットファクター": f"{profit_factor:.2f}",
                "勝率": f"{win_rate:.2f}%",
                "総トレード数": total_trades,
                "勝ちトレード数": win_trades,
                "負けトレード数": total_trades - win_trades,
                "平均利益": f"¥{avg_profit:,.2f}",
                "平均損失": f"¥{avg_loss:,.2f}",
                "リスクリワードレシオ": f"{risk_reward_ratio:.2f}"
            })

    if not all_results:
        logger.warning("有効なバックテスト結果がありませんでした。")
        return

    if not start_dates or not end_dates:
        logger.warning("有効なデータ期間が取得できなかったため、レポート生成をスキップします。")
        return

    overall_start = min(start_dates)
    overall_end = max(end_dates)

    report_df = report_generator.generate_report(all_results, strategy_params, overall_start, overall_end)

    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    summary_filename = f"summary_{timestamp}.csv"
    summary_path = os.path.join(config.REPORT_DIR, summary_filename)
    report_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    logger.info(f"サマリーレポートを保存しました: {summary_path}")

    if all_details:
        detail_df = pd.DataFrame(all_details).set_index('銘柄')
        detail_filename = f"detail_{timestamp}.csv"
        detail_path = os.path.join(config.REPORT_DIR, detail_filename)
        detail_df.to_csv(detail_path, encoding='utf-8-sig')
        logger.info(f"銘柄別詳細レポートを保存しました: {detail_path}")

    if all_trades:
        trades_df = pd.DataFrame(all_trades)
        trades_filename = f"trade_history_{timestamp}.csv"
        trades_path = os.path.join(config.REPORT_DIR, trades_filename)
        trades_df.to_csv(trades_path, index=False, encoding='utf-8-sig')
        logger.info(f"統合取引履歴を保存しました: {trades_path}")

    logger.info("\\n\\n★★★ 全銘柄バックテストサマリー ★★★\\n" + report_df.to_string())

    notifier.send_email(
        subject="【Backtrader】全銘柄バックテスト完了レポート",
        body=f"全てのバックテストが完了しました。\\n\\n--- サマリー ---\\n{report_df.to_string()}"
    )

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

logger = logging.getLogger(__name__)

# --- グローバル変数 ---
price_data_cache = {}
trade_history_df = None
strategy_params = None

def load_data():
    \"\"\"アプリケーション起動時に価格データと取引履歴を読み込む\"\"\"
    global trade_history_df, strategy_params

    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    if trade_history_path:
        trade_history_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
        logger.info(f"取引履歴ファイルを読み込みました: {trade_history_path}")
    else:
        trade_history_df = pd.DataFrame()
        logger.warning("取引履歴レポートが見つかりません。")

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
    \"\"\"指定されたプレフィックスを持つ最新のレポートファイルを見つける\"\"\"
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_all_symbols(data_dir):
    \"\"\"dataディレクトリから分析対象の全銘柄リストを取得する\"\"\"
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    files = glob.glob(file_pattern)
    symbols = [os.path.basename(f).split('_')[0] for f in files]
    return sorted(list(set(symbols)))

def get_trades_for_symbol(symbol):
    \"\"\"指定された銘柄の取引履歴を返す\"\"\"
    if trade_history_df is None or trade_history_df.empty:
        return pd.DataFrame()
    return trade_history_df[trade_history_df['銘柄'] == int(symbol)].copy()


def resample_ohlc(df, rule):
    \"\"\"価格データを指定の時間足にリサンプリングする\"\"\"
    df.index = pd.to_datetime(df.index)
    ohlc_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    return df.resample(rule).agg(ohlc_dict).dropna()

def generate_chart_json(symbol, timeframe_name, indicator_params):
    \"\"\"指定された銘柄と時間足のチャートを生成し、JSON形式で返す\"\"\"
    if symbol not in price_data_cache:
        return {}

    base_df = price_data_cache[symbol]
    symbol_trades = get_trades_for_symbol(symbol)

    p_ind = indicator_params
    p_tf = strategy_params['timeframes']
    p_filter = strategy_params['filters']
    
    df = None
    title = ""
    
    has_macd = False
    has_stoch = False
    has_bollinger = True

    if timeframe_name == 'short':
        df = base_df.copy()
        df['ema_fast'] = df['close'].ewm(span=p_ind['short_ema_fast'], adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=p_ind['short_ema_slow'], adjust=False).mean()
        
        # MACD
        exp1 = df['close'].ewm(span=p_ind['macd']['fast_period'], adjust=False).mean()
        exp2 = df['close'].ewm(span=p_ind['macd']['slow_period'], adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=p_ind['macd']['signal_period'], adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        has_macd = True

        # Slow Stochastic
        low_min = df['low'].rolling(window=p_ind['stochastic']['period']).min()
        high_max = df['high'].rolling(window=p_ind['stochastic']['period']).max()
        k_fast = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['stoch_k'] = k_fast.rolling(window=p_ind['stochastic']['period_dfast']).mean()
        df['stoch_d'] = df['stoch_k'].rolling(window=p_ind['stochastic']['period_dslow']).mean()
        has_stoch = True

        title = f"{symbol} Short-Term ({p_tf['short']['compression']}min) Interactive"

    elif timeframe_name == 'medium':
        df = resample_ohlc(base_df, f"{p_tf['medium']['compression']}min")
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        title = f"{symbol} Medium-Term ({p_tf['medium']['compression']}min) Interactive"
        
    elif timeframe_name == 'long':
        df = resample_ohlc(base_df, 'D')
        df['ema_long'] = df['close'].ewm(span=p_ind['long_ema_period'], adjust=False).mean()
        title = f'{symbol} Long-Term (Daily) Interactive'

    if df is None or df.empty:
        return {}

    p_bb = p_ind.get('bollinger', {})
    bb_period = p_bb.get('period', 20)
    bb_dev = p_bb.get('devfactor', 2.0)
    df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
    df['bb_std'] = df['close'].rolling(window=bb_period).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * bb_dev)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * bb_dev)

    has_rsi = 'rsi' in df.columns
    
    rows = 1
    row_heights = []
    specs = [[{"secondary_y": True}]]
    if has_rsi:
        rows += 1
        specs.append([{'secondary_y': False}])
    if has_macd:
        rows += 1
        specs.append([{'secondary_y': False}])
    if has_stoch:
        rows += 1
        specs.append([{'secondary_y': False}])
    
    if rows > 1:
        main_height = 1.0 - (0.15 * (rows - 1))
        sub_height = (1 - main_height) / (rows -1) if rows > 1 else 0
        row_heights = [main_height] + [sub_height] * (rows - 1)
    else:
        row_heights = [1]


    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, specs=specs, row_heights=row_heights)

    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), secondary_y=False, row=1, col=1)
    
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker=dict(color=volume_colors, opacity=0.3)), secondary_y=True, row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, hoverinfo='skip'), secondary_y=False, row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, fillcolor='rgba(128,128,128,0.1)', fill='tonexty', hoverinfo='skip'), secondary_y=False, row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], mode='lines', name=f"BB({bb_period}, {bb_dev})", line=dict(color='gray', width=0.7, dash='dash'), connectgaps=True), secondary_y=False, row=1, col=1)

    if 'ema_fast' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_fast'], mode='lines', name=f"EMA({p_ind['short_ema_fast']})", line=dict(color='blue', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if 'ema_slow' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_slow'], mode='lines', name=f"EMA({p_ind['short_ema_slow']})", line=dict(color='orange', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if 'ema_long' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['ema_long'], mode='lines', name=f"EMA({p_ind['long_ema_period']})", line=dict(color='purple', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    
    current_row = 2
    if has_rsi:
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=p_filter['medium_rsi_upper'], line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=p_filter['medium_rsi_lower'], line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="RSI", row=current_row, col=1, range=[0,100])
        current_row += 1
        
    if has_macd:
        macd_hist_colors = ['red' if val > 0 else 'green' for val in df['macd_hist']]
        fig.add_trace(go.Bar(x=df.index, y=df['macd_hist'], name='MACD Hist', marker_color=macd_hist_colors), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd'], mode='lines', name='MACD', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['macd_signal'], mode='lines', name='Signal', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="MACD", row=current_row, col=1)
        current_row += 1

    if has_stoch:
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_k'], mode='lines', name='%K', line=dict(color='blue', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['stoch_d'], mode='lines', name='%D', line=dict(color='orange', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="red", row=current_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="green", row=current_row, col=1)
        fig.update_yaxes(title_text="Stoch", row=current_row, col=1, range=[0,100])
        current_row += 1

    if not symbol_trades.empty:
        buy_trades = symbol_trades[symbol_trades['方向'] == 'BUY']
        sell_trades = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy_trades['エントリー日時'], y=buy_trades['エントリー価格'],mode='markers', name='Buy Entry',marker=dict(symbol='triangle-up', color='red', size=10)), secondary_y=False, row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_trades['エントリー日時'], y=sell_trades['エントリー価格'],mode='markers', name='Sell Entry', marker=dict(symbol='triangle-down', color='green', size=10)), secondary_y=False, row=1, col=1)
        for _, trade in symbol_trades.iterrows():
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['テイクプロフィット価格'],x1=trade['決済日時'], y1=trade['テイクプロフィット価格'],line=dict(color="red", width=2, dash="dash"),row=1, col=1, secondary_y=False)
            fig.add_shape(type="line",x0=trade['エントリー日時'], y0=trade['ストップロス価格'],x1=trade['決済日時'], y1=trade['ストップロス価格'],line=dict(color="green", width=2, dash="dash"),row=1, col=1, secondary_y=False)

    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Price", legend_title="Indicators", xaxis_rangeslider_visible=False, hovermode='x unified', autosize=True)
    fig.update_yaxes(title_text="Volume", secondary_y=True, row=1, col=1)

    if timeframe_name != 'long':
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[15, 9], pattern="hour"), dict(bounds=[11.5, 12.5], pattern="hour")])
    else:
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
        
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
    \"\"\"メインページを表示する。\"\"\"
    symbols = chart_generator.get_all_symbols(chart_generator.config.DATA_DIR)
    default_params = chart_generator.strategy_params['indicators']
    return render_template('index.html', symbols=symbols, params=default_params)

@app.route('/get_chart_data')
def get_chart_data():
    \"\"\"チャートと取引履歴のデータをまとめてJSONで返す。\"\"\"
    symbol = request.args.get('symbol', type=str)
    timeframe = request.args.get('timeframe', type=str)
    
    if not symbol or not timeframe:
        return jsonify({"error": "Symbol and timeframe are required"}), 400

    default_params = chart_generator.strategy_params['indicators']
    macd_defaults = default_params.get('macd', {})
    stoch_defaults = default_params.get('stochastic', {})
    bb_defaults = default_params.get('bollinger', {})
    
    indicator_params = {
        'long_ema_period': request.args.get('long_ema_period', default=default_params['long_ema_period'], type=int),
        'medium_rsi_period': request.args.get('medium_rsi_period', default=default_params['medium_rsi_period'], type=int),
        'short_ema_fast': request.args.get('short_ema_fast', default=default_params['short_ema_fast'], type=int),
        'short_ema_slow': request.args.get('short_ema_slow', default=default_params['short_ema_slow'], type=int),
        'macd': {
            'fast_period': request.args.get('macd_fast_period', default=macd_defaults.get('fast_period'), type=int),
            'slow_period': request.args.get('macd_slow_period', default=macd_defaults.get('slow_period'), type=int),
            'signal_period': request.args.get('macd_signal_period', default=macd_defaults.get('signal_period'), type=int),
        },
        'stochastic': {
            'period': request.args.get('stoch_period', default=stoch_defaults.get('period'), type=int),
            'period_dfast': request.args.get('stoch_period_dfast', default=stoch_defaults.get('period_dfast'), type=int),
            'period_dslow': request.args.get('stoch_period_dslow', default=stoch_defaults.get('period_dslow'), type=int),
        },
        'bollinger': {
            'period': request.args.get('bollinger_period', default=bb_defaults.get('period'), type=int),
            'devfactor': request.args.get('bollinger_devfactor', default=bb_defaults.get('devfactor'), type=float),
        }
    }

    chart_json = chart_generator.generate_chart_json(symbol, timeframe, indicator_params)
    trades_df = chart_generator.get_trades_for_symbol(symbol)
    
    trades_df = trades_df.where(pd.notnull(trades_df), None)

    trades_df['損益'] = trades_df['損益'].round(2)
    trades_df['損益(手数料込)'] = trades_df['損益(手数料込)'].round(2)

    trades_json = trades_df.to_json(orient='records')
    
    return jsonify(chart=chart_json, trades=trades_json)

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
        html, body { height: 100%; margin: 0; padding: 0; overflow: hidden; font-family: sans-serif; background-color: #f4f4f4; }
        .container { display: flex; flex-direction: column; height: 100%; padding: 15px; box-sizing: border-box; }
        .controls { margin-bottom: 15px; display: flex; flex-wrap: wrap; gap: 15px; align-items: center; flex-shrink: 0; background-color: #fff; padding: 10px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .control-group { display: flex; flex-direction: column; }
        label { font-weight: bold; font-size: 0.8em; margin-bottom: 4px; color: #555;}
        select, input[type="number"] { padding: 8px; border-radius: 4px; border: 1px solid #ddd; width: 100px; }
        #chart-container { flex-grow: 1; position: relative; min-height: 300px; }
        #chart { width: 100%; height: 100%; }
        .loader { border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 60px; height: 60px; animation: spin 2s linear infinite; position: absolute; top: 50%; left: 50%; margin-top: -30px; margin-left: -30px; display: none; }
        #table-container { flex-shrink: 0; max-height: 35%; overflow: auto; margin-top: 15px; } /* 縦横スクロール可能に */
        table { border-collapse: collapse; width: 100%; font-size: 0.8em; white-space: nowrap; }
        th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
        th { background-color: #f2f2f2; position: sticky; top: 0; }
        tbody tr:hover { background-color: #f5f5f5; cursor: pointer; }
        tbody tr.highlighted { background-color: #fff8dc; } /* ハイライト用のスタイル */
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
    <div class="container">
        <h1>Interactive Chart Viewer</h1>
        <div class="controls">
            <div class="control-group">
                <label for="symbol-select">銘柄</label>
                <select id="symbol-select">
                    {% for symbol in symbols %}
                        <option value="{{ symbol }}">{{ symbol }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="control-group">
                <label for="timeframe-select">時間足</label>
                <select id="timeframe-select">
                    <option value="short">短期 (Short)</option>
                    <option value="medium">中期 (Medium)</option>
                    <option value="long">長期 (Long)</option>
                </select>
            </div>
            <div class="control-group">
                <label for="short-ema-fast">短期EMA(速)</label>
                <input type="number" id="short-ema-fast" value="{{ params.short_ema_fast }}">
            </div>
            <div class="control-group">
                <label for="short-ema-slow">短期EMA(遅)</label>
                <input type="number" id="short-ema-slow" value="{{ params.short_ema_slow }}">
            </div>
             <div class="control-group">
                <label for="macd-fast-period">MACD(速)</label>
                <input type="number" id="macd-fast-period" value="{{ params.macd.fast_period }}">
            </div>
            <div class="control-group">
                <label for="macd-slow-period">MACD(遅)</label>
                <input type="number" id="macd-slow-period" value="{{ params.macd.slow_period }}">
            </div>
             <div class="control-group">
                <label for="macd-signal-period">MACD(シグナル)</label>
                <input type="number" id="macd-signal-period" value="{{ params.macd.signal_period }}">
            </div>
             <div class="control-group">
                <label for="stoch-period">Stoch %K</label>
                <input type="number" id="stoch-period" value="{{ params.stochastic.period }}">
            </div>
            <div class="control-group">
                <label for="stoch-period-dfast">Stoch Slow %K</label>
                <input type="number" id="stoch-period-dfast" value="{{ params.stochastic.period_dfast }}">
            </div>
            <div class="control-group">
                <label for="stoch-period-dslow">Stoch %D</label>
                <input type="number" id="stoch-period-dslow" value="{{ params.stochastic.period_dslow }}">
            </div>
             <div class="control-group">
                <label for="bollinger-period">BB Period</label>
                <input type="number" id="bollinger-period" value="{{ params.bollinger.period }}">
            </div>
            <div class="control-group">
                <label for="bollinger-devfactor">BB StdDev</label>
                <input type="number" id="bollinger-devfactor" step="0.1" value="{{ params.bollinger.devfactor }}">
            </div>
            <div class="control-group">
                <label for="medium-rsi-period">中期RSI</label>
                <input type="number" id="medium-rsi-period" value="{{ params.medium_rsi_period }}">
            </div>
            <div class="control-group">
                <label for="long-ema-period">長期EMA</label>
                <input type="number" id="long-ema-period" value="{{ params.long_ema_period }}">
            </div>
        </div>
        <div id="chart-container">
            <div id="loader" class="loader"></div>
            <div id="chart"></div>
        </div>
        <div id="table-container">
             <table id="trades-table">
                <thead>
                    <tr>
                        <th>方向</th>
                        <th>数量</th>
                        <th>エントリー価格</th>
                        <th>エントリー日時</th>
                        <th>エントリー根拠</th>
                        <th>決済価格</th>
                        <th>決済日時</th>
                        <th>決済根拠</th>
                        <th>損益</th>
                        <th>損益(手数料込)</th>
                        <th>SL価格</th>
                        <th>TP価格</th>
                        <th>長期EMA</th>
                        <th>中期RSI</th>
                    </tr>
                </thead>
                <tbody>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const controls = document.querySelectorAll('.controls select, .controls input');
        const chartDiv = document.getElementById('chart');
        const loader = document.getElementById('loader');
        const tableBody = document.querySelector("#trades-table tbody");
        
        function formatDateTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            const Y = date.getFullYear();
            const M = (date.getMonth() + 1).toString().padStart(2, '0');
            const D = date.getDate().toString().padStart(2, '0');
            const h = date.getHours().toString().padStart(2, '0');
            const m = date.getMinutes().toString().padStart(2, '0');
            const s = date.getSeconds().toString().padStart(2, '0');
            return `${Y}-${M}-${D} ${h}:${m}:${s}`;
        }

        function formatNumber(num, digits = 2) {
             if (num === null || typeof num === 'undefined' || isNaN(num)) return '';
             return num.toFixed(digits);
        }

        function updateChart() {
            const symbol = document.getElementById('symbol-select').value;
            const timeframe = document.getElementById('timeframe-select').value;
            
            const params = {
                symbol, timeframe,
                short_ema_fast: document.getElementById('short-ema-fast').value,
                short_ema_slow: document.getElementById('short-ema-slow').value,
                medium_rsi_period: document.getElementById('medium-rsi-period').value,
                long_ema_period: document.getElementById('long-ema-period').value,
                macd_fast_period: document.getElementById('macd-fast-period').value,
                macd_slow_period: document.getElementById('macd-slow-period').value,
                macd_signal_period: document.getElementById('macd-signal-period').value,
                stoch_period: document.getElementById('stoch-period').value,
                stoch_period_dfast: document.getElementById('stoch-period-dfast').value,
                stoch_period_dslow: document.getElementById('stoch-period-dslow').value,
                bollinger_period: document.getElementById('bollinger-period').value,
                bollinger_devfactor: document.getElementById('bollinger-devfactor').value,
            };

            loader.style.display = 'block';
            chartDiv.style.display = 'none';
            tableBody.innerHTML = '';

            const query = new URLSearchParams(params);

            fetch(`/get_chart_data?${query.toString()}`)
                .then(response => response.json())
                .then(data => {
                    const chartJson = JSON.parse(data.chart);
                    const trades = JSON.parse(data.trades);

                    if (chartJson.data && chartJson.layout) {
                        Plotly.newPlot('chart', chartJson.data, chartJson.layout, {responsive: true, scrollZoom: true});
                    }
                    if (trades) {
                        buildTradeTable(trades);
                    }
                })
                .catch(error => { console.error('Error fetching data:', error); })
                .finally(() => {
                    loader.style.display = 'none';
                    chartDiv.style.display = 'block';
                    window.dispatchEvent(new Event('resize'));
                });
        }
        
        function buildTradeTable(trades) {
            tableBody.innerHTML = '';
            trades.forEach(trade => {
                const row = tableBody.insertRow();
                row.innerHTML = `
                    <td>${trade['方向']}</td>
                    <td>${formatNumber(trade['数量'], 2)}</td>
                    <td>${formatNumber(trade['エントリー価格'])}</td>
                    <td>${formatDateTime(trade['エントリー日時'])}</td>
                    <td>${trade['エントリー根拠']}</td>
                    <td>${formatNumber(trade['決済価格'])}</td>
                    <td>${formatDateTime(trade['決済日時'])}</td>
                    <td>${trade['決済根拠']}</td>
                    <td>${formatNumber(trade['損益'])}</td>
                    <td>${formatNumber(trade['損益(手数料込)'])}</td>
                    <td>${formatNumber(trade['ストップロス価格'])}</td>
                    <td>${formatNumber(trade['テイクプロフィット価格'])}</td>
                    <td>${formatNumber(trade['エントリー時長期EMA'])}</td>
                    <td>${formatNumber(trade['エントリー時中期RSI'])}</td>
                `;
                
                row.addEventListener('click', (event) => {
                    document.querySelectorAll('#trades-table tbody tr').forEach(tr => tr.classList.remove('highlighted'));
                    event.currentTarget.classList.add('highlighted');
                    highlightTradeOnChart(trade)
                });
            });
        }

        function highlightTradeOnChart(trade) {
            const chartDataX = chartDiv.data[0].x; 
            const entryTime = new Date(trade['エントリー日時']);
            const exitTime = new Date(trade['決済日時']);

            let highlightStartTime = null;
            for (let i = chartDataX.length - 1; i >= 0; i--) {
                if (new Date(chartDataX[i]) <= entryTime) {
                    highlightStartTime = chartDataX[i];
                    break;
                }
            }

            let highlightEndTime = null;
            let endIndex = -1;
            for (let i = chartDataX.length - 1; i >= 0; i--) {
                if (new Date(chartDataX[i]) <= exitTime) {
                    highlightEndTime = chartDataX[i];
                    endIndex = i;
                    break;
                }
            }
            
            if (!highlightStartTime || !highlightEndTime) return;

            let highlightVisualEndTime = (endIndex < chartDataX.length - 1) ? chartDataX[endIndex + 1] : highlightEndTime;

            const currentLayout = chartDiv.layout;
            currentLayout.shapes = (currentLayout.shapes || []).filter(s => s.name !== 'highlight-shape');
            
            currentLayout.shapes.push({
                name: 'highlight-shape',
                type: 'rect',
                xref: 'x',
                yref: 'paper',
                x0: highlightStartTime,
                y0: 0,
                x1: highlightVisualEndTime,
                y1: 1,
                fillcolor: 'rgba(255, 255, 0, 0.9)',
                line: { width: 0 },
                layer: 'below'
            });

            Plotly.relayout('chart', {
                'shapes': currentLayout.shapes
            });
        }

        window.addEventListener('resize', () => {
            if(chartDiv.childElementCount > 0) {
                 Plotly.Plots.resize(chartDiv);
            }
        });

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
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
            
        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"ファイルを作成しました: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("プロジェクトファイルの生成を開始します...")
    create_files(project_files)
    print("\nプロジェクトファイルの生成が完了しました。")
    print("\n--- 実行方法 ---")
    print("1. 必要なライブラリをインストールします: pip install -r requirements.txt")
    print("2. バックテストを実行します（初回のみ）: python run_backtrader.py")
    print("3. Webアプリケーションを起動します: python app.py")
    print("4. Webブラウザで http://127.0.0.1:5001 を開きます。")
