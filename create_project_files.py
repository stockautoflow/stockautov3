# ==============================================================================
# ファイル: create_project_files.py
# 説明: このスクリプトは、チャート生成機能に「一目均衡表」と「ADX」を追加した
#       株自動トレードシステムの全てのファイルを生成します。
# バージョン: v65
# 主な機能:
#   - FlaskによるWebアプリケーションとして動作。
#   - Web UIから銘柄、時間足、全インジケーターのパラメータを動的に変更可能。
#   - Plotlyによるインタラクティブなチャート描画。
#   - 短期・中期・長期の全時間足にADX/DMIを表示。
#   - 短期チャートの一目均衡表の先行スパンA/Bを線画表示。
#   - ボリンジャーバンドの表示を修正。(v65で修正)
#   - チャートと取引履歴テーブルの連動（クリックでハイライト）。
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
  ichimoku:
    tenkan_period: 9
    kijun_period: 26
    senkou_span_b_period: 52
    chikou_period: 26
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
    "btrader_strategy.py": """import backtrader as bt
import yaml
import logging

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
        p_ichi = p_ind.get('ichimoku', {})
        p_adx = p_ind.get('adx', {})
        adx_period = p_adx.get('period', 14)

        self.short_data = self.datas[0]
        self.medium_data = self.datas[1]
        self.long_data = self.datas[2]

        self.long_ema = bt.indicators.EMA(self.long_data.close, period=p_ind['long_ema_period'])
        self.medium_rsi = bt.indicators.RSI(self.medium_data.close, period=p_ind['medium_rsi_period'])

        self.short_ema_fast = bt.indicators.EMA(self.short_data.close, period=p_ind['short_ema_fast'])
        self.short_ema_slow = bt.indicators.EMA(self.short_data.close, period=p_ind['short_ema_slow'])
        self.short_cross = bt.indicators.CrossOver(self.short_ema_fast, self.short_ema_slow)
        self.atr = bt.indicators.ATR(self.short_data, period=p_ind['atr_period'])

        self.short_adx = bt.indicators.AverageDirectionalMovementIndex(self.short_data, period=adx_period)
        self.medium_adx = bt.indicators.AverageDirectionalMovementIndex(self.medium_data, period=adx_period)
        self.long_adx = bt.indicators.AverageDirectionalMovementIndex(self.long_data, period=adx_period)

        self.macd = bt.indicators.MACD(self.short_data.close, period_me1=p_macd.get('fast_period', 12),
                                       period_me2=p_macd.get('slow_period', 26), period_signal=p_macd.get('signal_period', 9))
        self.stochastic = bt.indicators.StochasticSlow(self.short_data, period=p_stoch.get('period', 14),
                                                        period_dfast=p_stoch.get('period_dfast', 3), period_dslow=p_stoch.get('period_dslow', 3))
        self.ichimoku = bt.indicators.Ichimoku(self.short_data, tenkan=p_ichi.get('tenkan_period', 9), kijun=p_ichi.get('kijun_period', 26),
                                               senkou=p_ichi.get('senkou_span_b_period', 52), senkou_lead=p_ichi.get('kijun_period', 26),
                                               chikou=p_ichi.get('chikou_period', 26))

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
                if size <= 0: return
                self.entry_reason = f"L:C>EMA, M:RSI OK, S:GoldenCross"
                self.log(f"BUY CREATE, Price: {self.short_data.close[0]:.2f}, Size: {size:.2f}")
                self.order = self.buy_bracket(size=size, price=self.short_data.close[0], limitprice=self.tp_price, stopprice=self.sl_price)
                return

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
                if size <= 0: return
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
                'medium_rsi': self.strategy.medium_rsi[0],
                'tenkan_sen': self.strategy.ichimoku.tenkan[0],
                'kijun_sen': self.strategy.ichimoku.kijun[0],
                'short_adx': self.strategy.short_adx.adx[0],
                'medium_adx': self.strategy.medium_adx.adx[0],
                'long_adx': self.strategy.long_adx.adx[0],
            }
            return

        if trade.isclosed:
            p = self.strategy.strategy_params
            exit_rules = p['exit_rules']
            if trade.pnl >= 0: exit_reason = f"Take Profit (ATR x{exit_rules['take_profit_atr_multiplier']})"
            else: exit_reason = f"Stop Loss (ATR x{exit_rules['stop_loss_atr_multiplier']})"
            info = self.entry_info.pop(trade.ref, {})
            original_size = info.get('size', 0)
            entry_dt_naive = bt.num2date(trade.dtopen).replace(tzinfo=None)
            close_dt_naive = bt.num2date(trade.dtclose).replace(tzinfo=None)
            exit_price = trade.price + (trade.pnl / original_size) if original_size else 0
            self.trades.append({
                '銘柄': self.symbol, '方向': 'BUY' if trade.long else 'SELL', '数量': original_size,
                'エントリー価格': trade.price, 'エントリー日時': entry_dt_naive.isoformat(), 'エントリー根拠': info.get('entry_reason', "N/A"),
                '決済価格': exit_price, '決済日時': close_dt_naive.isoformat(), '決済根拠': exit_reason,
                '損益': trade.pnl, '損益(手数料込)': trade.pnlcomm,
                'ストップロス価格': info.get('stop_loss_price', 0), 'テイクプロフィット価格': info.get('take_profit_price', 0),
                'エントリー時長期EMA': info.get('long_ema', 0), 'エントリー時中期RSI': info.get('medium_rsi', 0),
                'エントリー時転換線': info.get('tenkan_sen', 0), 'エントリー時基準線': info.get('kijun_sen', 0),
                'エントリー時短期ADX': info.get('short_adx', 0), 'エントリー時中期ADX': info.get('medium_adx', 0), 'エントリー時長期ADX': info.get('long_adx', 0),
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
    with open('strategy.yml', 'r', encoding='utf-8') as f: strategy_params = yaml.safe_load(f)
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
    raw_stats = {'symbol': symbol, 'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0),
                 'gross_won': trade_analysis.get('won', {}).get('pnl', {}).get('total', 0), 'gross_lost': trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0),
                 'total_trades': trade_analysis.get('total', {}).get('total', 0), 'win_trades': trade_analysis.get('won', {}).get('total', 0)}
    return raw_stats, dataframe.index[0], dataframe.index[-1], trade_list

def main():
    logger_setup.setup_logging()
    logger.info("--- 全銘柄バックテスト開始 ---")
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path): os.makedirs(dir_path)
    with open('strategy.yml', 'r', encoding='utf-8') as f: strategy_params = yaml.safe_load(f)
    csv_files = get_csv_files(config.DATA_DIR)
    if not csv_files:
        logger.error(f"{config.DATA_DIR} に指定された形式のCSVデータが見つかりません。")
        return
    all_results, all_trades, all_details, start_dates, end_dates = [], [], [], [], []
    for filepath in csv_files:
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(filepath, btrader_strategy.MultiTimeFrameStrategy)
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
            all_details.append({"銘柄": stats['symbol'], "純利益": f"¥{stats['pnl_net']:,.2f}", "総利益": f"¥{gross_won:,.2f}", "総損失": f"¥{gross_lost:,.2f}",
                                "プロフィットファクター": f"{profit_factor:.2f}", "勝率": f"{win_rate:.2f}%", "総トレード数": total_trades, "勝ちトレード数": win_trades,
                                "負けトレード数": total_trades - win_trades, "平均利益": f"¥{avg_profit:,.2f}", "平均損失": f"¥{avg_loss:,.2f}", "リスクリワードレシオ": f"{risk_reward_ratio:.2f}"})
    if not all_results:
        logger.warning("有効なバックテスト結果がありませんでした。")
        return
    if not start_dates or not end_dates:
        logger.warning("有効なデータ期間が取得できなかったため、レポート生成をスキップします。")
        return
    overall_start, overall_end = min(start_dates), max(end_dates)
    report_df = report_generator.generate_report(all_results, strategy_params, overall_start, overall_end)
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    summary_filename = f"summary_{timestamp}.csv"
    summary_path = os.path.join(config.REPORT_DIR, summary_filename)
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
        logger.warning("取引履歴レポートが見つかりません。")
    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f: strategy_params = yaml.safe_load(f)
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
            if df.index.tz is not None: df.index = df.index.tz_localize(None)
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
    if trade_history_df is None or trade_history_df.empty: return pd.DataFrame()
    return trade_history_df[trade_history_df['銘柄'] == int(symbol)].copy()

def resample_ohlc(df, rule):
    df.index = pd.to_datetime(df.index)
    ohlc_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    return df.resample(rule).agg(ohlc_dict).dropna()

def add_adx(df, params):
    p = params.get('adx', {})
    period = p.get('period', 14)
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    up_move = high - high.shift()
    down_move = low.shift() - low
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-9)
    df['adx'] = dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    df['plus_di'] = plus_di
    df['minus_di'] = minus_di
    return df

def add_ichimoku(df, params):
    p = params['ichimoku']
    high, low, close = df['high'], df['low'], df['close']
    tenkan_high = high.rolling(window=p['tenkan_period']).max()
    tenkan_low = low.rolling(window=p['tenkan_period']).min()
    df['tenkan_sen'] = (tenkan_high + tenkan_low) / 2
    kijun_high = high.rolling(window=p['kijun_period']).max()
    kijun_low = low.rolling(window=p['kijun_period']).min()
    df['kijun_sen'] = (kijun_high + kijun_low) / 2
    df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(p['kijun_period'])
    senkou_b_high = high.rolling(window=p['senkou_span_b_period']).max()
    senkou_b_low = low.rolling(window=p['senkou_span_b_period']).min()
    df['senkou_span_b'] = ((senkou_b_high + senkou_b_low) / 2).shift(p['kijun_period'])
    df['chikou_span'] = close.shift(-p['chikou_period'])
    return df

def generate_chart_json(symbol, timeframe_name, indicator_params):
    if symbol not in price_data_cache: return {}
    base_df = price_data_cache[symbol]
    symbol_trades = get_trades_for_symbol(symbol)
    p_ind = indicator_params
    p_tf = strategy_params['timeframes']
    p_filter = strategy_params['filters']
    df, title = None, ""
    has_ichimoku, has_macd, has_stoch, has_rsi = False, False, False, False

    if timeframe_name == 'short':
        df = base_df.copy()
        df['ema_fast'] = df['close'].ewm(span=p_ind['short_ema_fast'], adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=p_ind['short_ema_slow'], adjust=False).mean()
        df = add_ichimoku(df, p_ind); has_ichimoku = True
        exp1 = df['close'].ewm(span=p_ind['macd']['fast_period'], adjust=False).mean()
        exp2 = df['close'].ewm(span=p_ind['macd']['slow_period'], adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=p_ind['macd']['signal_period'], adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']; has_macd = True
        low_min = df['low'].rolling(window=p_ind['stochastic']['period']).min()
        high_max = df['high'].rolling(window=p_ind['stochastic']['period']).max()
        k_fast = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['stoch_k'] = k_fast.rolling(window=p_ind['stochastic']['period_dfast']).mean()
        df['stoch_d'] = df['stoch_k'].rolling(window=p_ind['stochastic']['period_dslow']).mean(); has_stoch = True
        title = f"{symbol} Short-Term ({p_tf['short']['compression']}min) Interactive"
    elif timeframe_name == 'medium':
        df = resample_ohlc(base_df, f"{p_tf['medium']['compression']}min")
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs)); has_rsi = True
        title = f"{symbol} Medium-Term ({p_tf['medium']['compression']}min) Interactive"
    elif timeframe_name == 'long':
        df = resample_ohlc(base_df, 'D')
        df['ema_long'] = df['close'].ewm(span=p_ind['long_ema_period'], adjust=False).mean()
        title = f'{symbol} Long-Term (Daily) Interactive'

    if df is None or df.empty: return {}
    
    df = add_adx(df, p_ind)
    has_adx = True

    p_bb = p_ind.get('bollinger', {})
    bb_period, bb_dev = p_bb.get('period', 20), p_bb.get('devfactor', 2.0)
    df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
    df['bb_std'] = df['close'].rolling(window=bb_period).std()
    df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * bb_dev)
    df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * bb_dev)

    sub_indicators = [has_adx, has_rsi, has_macd, has_stoch]
    rows = 1 + sum(sub_indicators)
    specs = [[{"secondary_y": True}]] + [[{'secondary_y': False}] for _ in range(sum(sub_indicators))]
    main_height = 1.0 - (0.15 * sum(sub_indicators))
    sub_height = (1 - main_height) / sum(sub_indicators) if sum(sub_indicators) > 0 else 0
    row_heights = [main_height] + [sub_height] * sum(sub_indicators) if sum(sub_indicators) > 0 else [1]
    
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, specs=specs, row_heights=row_heights)
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='OHLC', increasing_line_color='red', decreasing_line_color='green'), secondary_y=False, row=1, col=1)
    volume_colors = ['red' if row.close > row.open else 'green' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], name='Volume', marker=dict(color=volume_colors, opacity=0.3)), secondary_y=True, row=1, col=1)
    
    # Add Bollinger Bands
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_upper'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, hoverinfo='skip'), secondary_y=False, row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_lower'], mode='lines', line=dict(color='gray', width=0.5), showlegend=False, connectgaps=True, fillcolor='rgba(128,128,128,0.1)', fill='tonexty', hoverinfo='skip'), secondary_y=False, row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['bb_middle'], mode='lines', name=f"BB({bb_period}, {bb_dev})", line=dict(color='gray', width=0.7, dash='dash'), connectgaps=True), secondary_y=False, row=1, col=1)

    if 'ema_fast' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['ema_fast'], mode='lines', name=f"EMA({p_ind['short_ema_fast']})", line=dict(color='#007bff', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if 'ema_slow' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['ema_slow'], mode='lines', name=f"EMA({p_ind['short_ema_slow']})", line=dict(color='#ff7f0e', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    if 'ema_long' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['ema_long'], mode='lines', name=f"EMA({p_ind['long_ema_period']})", line=dict(color='#9467bd', width=1), connectgaps=True), secondary_y=False, row=1, col=1)
    
    if has_ichimoku:
        fig.add_trace(go.Scatter(x=df.index, y=df['tenkan_sen'], mode='lines', name='転換線', line=dict(color='blue', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['kijun_sen'], mode='lines', name='基準線', line=dict(color='red', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['chikou_span'], mode='lines', name='遅行スパン', line=dict(color='#8c564b', width=1.5, dash='dash'), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_a'], mode='lines', name='先行A', line=dict(color='rgba(0, 200, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['senkou_span_b'], mode='lines', name='先行B', line=dict(color='rgba(200, 0, 0, 0.8)', width=1), connectgaps=True), row=1, col=1)

    current_row = 2
    if has_adx:
        fig.add_trace(go.Scatter(x=df.index, y=df['adx'], mode='lines', name='ADX', line=dict(color='black', width=1.5), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['plus_di'], mode='lines', name='+DI', line=dict(color='green', width=1), connectgaps=True), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['minus_di'], mode='lines', name='-DI', line=dict(color='red', width=1), connectgaps=True), row=current_row, col=1)
        fig.update_yaxes(title_text="ADX", row=current_row, col=1, range=[0, 100])
        current_row += 1
    if has_rsi:
        fig.add_trace(go.Scatter(x=df.index, y=df['rsi'], mode='lines', name='RSI', line=dict(color='#1f77b4', width=1), connectgaps=True), row=current_row, col=1)
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

    if not symbol_trades.empty:
        buy_trades = symbol_trades[symbol_trades['方向'] == 'BUY']; sell_trades = symbol_trades[symbol_trades['方向'] == 'SELL']
        fig.add_trace(go.Scatter(x=buy_trades['エントリー日時'], y=buy_trades['エントリー価格'],mode='markers', name='Buy',marker=dict(symbol='triangle-up', color='red', size=10)), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_trades['エントリー日時'], y=sell_trades['エントリー価格'],mode='markers', name='Sell', marker=dict(symbol='triangle-down', color='green', size=10)), row=1, col=1)
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
    default_params = chart_generator.strategy_params['indicators']
    return render_template('index.html', symbols=symbols, params=default_params)

@app.route('/get_chart_data')
def get_chart_data():
    symbol = request.args.get('symbol', type=str)
    timeframe = request.args.get('timeframe', type=str)
    if not symbol or not timeframe:
        return jsonify({"error": "Symbol and timeframe are required"}), 400

    p = chart_generator.strategy_params['indicators']
    indicator_params = {
        'long_ema_period': request.args.get('long_ema_period', default=p.get('long_ema_period'), type=int),
        'medium_rsi_period': request.args.get('medium_rsi_period', default=p.get('medium_rsi_period'), type=int),
        'short_ema_fast': request.args.get('short_ema_fast', default=p.get('short_ema_fast'), type=int),
        'short_ema_slow': request.args.get('short_ema_slow', default=p.get('short_ema_slow'), type=int),
        'adx': {'period': request.args.get('adx_period', default=p.get('adx', {}).get('period'), type=int)},
        'macd': {
            'fast_period': request.args.get('macd_fast_period', default=p.get('macd', {}).get('fast_period'), type=int),
            'slow_period': request.args.get('macd_slow_period', default=p.get('macd', {}).get('slow_period'), type=int),
            'signal_period': request.args.get('macd_signal_period', default=p.get('macd', {}).get('signal_period'), type=int),
        },
        'stochastic': {
            'period': request.args.get('stoch_period', default=p.get('stochastic', {}).get('period'), type=int),
            'period_dfast': request.args.get('stoch_period_dfast', default=p.get('stochastic', {}).get('period_dfast'), type=int),
            'period_dslow': request.args.get('stoch_period_dslow', default=p.get('stochastic', {}).get('period_dslow'), type=int),
        },
        'bollinger': {
            'period': request.args.get('bollinger_period', default=p.get('bollinger', {}).get('period'), type=int),
            'devfactor': request.args.get('bollinger_devfactor', default=p.get('bollinger', {}).get('devfactor'), type=float),
        },
        'ichimoku': {
            'tenkan_period': request.args.get('ichimoku_tenkan_period', default=p.get('ichimoku', {}).get('tenkan_period'), type=int),
            'kijun_period': request.args.get('ichimoku_kijun_period', default=p.get('ichimoku', {}).get('kijun_period'), type=int),
            'senkou_span_b_period': request.args.get('ichimoku_senkou_b_period', default=p.get('ichimoku', {}).get('senkou_span_b_period'), type=int),
            'chikou_period': request.args.get('ichimoku_chikou_period', default=p.get('ichimoku', {}).get('chikou_period'), type=int),
        }
    }

    chart_json = chart_generator.generate_chart_json(symbol, timeframe, indicator_params)
    trades_df = chart_generator.get_trades_for_symbol(symbol)
    trades_df = trades_df.where(pd.notnull(trades_df), None)
    for col in ['損益', '損益(手数料込)']:
        if col in trades_df.columns: trades_df[col] = trades_df[col].round(2)
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
        .controls { margin-bottom: 15px; display: flex; flex-wrap: wrap; gap: 10px 15px; align-items: flex-end; flex-shrink: 0; background-color: #fff; padding: 10px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .control-group { display: flex; flex-direction: column; }
        .control-group legend { font-weight: bold; font-size: 0.9em; margin-bottom: 5px; color: #333; padding: 0 3px; border-bottom: 2px solid #3498db;}
        .control-group fieldset { border: 1px solid #ccc; border-radius: 4px; padding: 8px; display: flex; gap: 10px;}
        label { font-weight: bold; font-size: 0.8em; margin-bottom: 4px; color: #555;}
        select, input[type="number"] { padding: 8px; border-radius: 4px; border: 1px solid #ddd; width: 80px; }
        #chart-container { flex-grow: 1; position: relative; min-height: 300px; }
        #chart { width: 100%; height: 100%; }
        .loader { border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 60px; height: 60px; animation: spin 2s linear infinite; position: absolute; top: 50%; left: 50%; margin-top: -30px; margin-left: -30px; display: none; }
        #table-container { flex-shrink: 0; max-height: 30%; overflow: auto; margin-top: 15px; }
        table { border-collapse: collapse; width: 100%; font-size: 0.8em; white-space: nowrap; }
        th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
        th { background-color: #f2f2f2; position: sticky; top: 0; z-index: 1;}
        tbody tr:hover { background-color: #f5f5f5; cursor: pointer; }
        tbody tr.highlighted { background-color: #fff8dc; }
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
                <select id="symbol-select">{% for symbol in symbols %}<option value="{{ symbol }}">{{ symbol }}</option>{% endfor %}</select>
            </div>
            <div class="control-group">
                <label for="timeframe-select">時間足</label>
                <select id="timeframe-select">
                    <option value="short" selected>短期 (Short)</option><option value="medium">中期 (Medium)</option><option value="long">長期 (Long)</option>
                </select>
            </div>
            <div class="control-group">
                <legend>ADX</legend>
                 <fieldset>
                    <div class="control-group">
                        <label for="adx-period">ADX Period</label>
                        <input type="number" id="adx-period" value="{{ params.adx.period }}">
                    </div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>Ichimoku (Short Only)</legend>
                 <fieldset>
                    <div class="control-group"><label for="ichimoku-tenkan-period">転換線</label><input type="number" id="ichimoku-tenkan-period" value="{{ params.ichimoku.tenkan_period }}"></div>
                    <div class="control-group"><label for="ichimoku-kijun-period">基準線</label><input type="number" id="ichimoku-kijun-period" value="{{ params.ichimoku.kijun_period }}"></div>
                    <div class="control-group"><label for="ichimoku-senkou-b-period">先行S2</label><input type="number" id="ichimoku-senkou-b-period" value="{{ params.ichimoku.senkou_span_b_period }}"></div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>EMA/BB</legend>
                 <fieldset>
                    <div class="control-group"><label for="short-ema-fast">短期EMA(速)</label><input type="number" id="short-ema-fast" value="{{ params.short_ema_fast }}"></div>
                    <div class="control-group"><label for="short-ema-slow">短期EMA(遅)</label><input type="number" id="short-ema-slow" value="{{ params.short_ema_slow }}"></div>
                    <div class="control-group"><label for="bollinger-period">BB Period</label><input type="number" id="bollinger-period" value="{{ params.bollinger.period }}"></div>
                    <div class="control-group"><label for="bollinger-devfactor">BB StdDev</label><input type="number" id="bollinger-devfactor" step="0.1" value="{{ params.bollinger.devfactor }}"></div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>Oscillators</legend>
                 <fieldset>
                     <div class="control-group"><label for="macd-fast-period">MACD(速)</label><input type="number" id="macd-fast-period" value="{{ params.macd.fast_period }}"></div>
                    <div class="control-group"><label for="macd-slow-period">MACD(遅)</label><input type="number" id="macd-slow-period" value="{{ params.macd.slow_period }}"></div>
                     <div class="control-group"><label for="macd-signal-period">MACD(Sig)</label><input type="number" id="macd-signal-period" value="{{ params.macd.signal_period }}"></div>
                     <div class="control-group"><label for="stoch-period">Stoch %K</label><input type="number" id="stoch-period" value="{{ params.stochastic.period }}"></div>
                 </fieldset>
            </div>
            <div class="control-group">
                <legend>Other TFs Ind.</legend>
                 <fieldset>
                    <div class="control-group"><label for="medium-rsi-period">中期RSI</label><input type="number" id="medium-rsi-period" value="{{ params.medium_rsi_period }}"></div>
                    <div class="control-group"><label for="long-ema-period">長期EMA</label><input type="number" id="long-ema-period" value="{{ params.long_ema_period }}"></div>
                 </fieldset>
            </div>
        </div>
        <div id="chart-container"><div id="loader" class="loader"></div><div id="chart"></div></div>
        <div id="table-container">
             <table id="trades-table">
                <thead>
                    <tr>
                        <th>方向</th><th>数量</th><th>エントリー価格</th><th>日時</th><th>根拠</th>
                        <th>決済価格</th><th>日時</th><th>根拠</th><th>損益</th><th>損益(込)</th>
                        <th>SL</th><th>TP</th><th>長期EMA</th><th>中期RSI</th>
                        <th>転換線</th><th>基準線</th>
                        <th>短期ADX</th><th>中期ADX</th><th>長期ADX</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <script>
        const controls = document.querySelectorAll('.controls select, .controls input');
        const chartDiv = document.getElementById('chart');
        const loader = document.getElementById('loader');
        const tableBody = document.querySelector("#trades-table tbody");
        
        function formatDateTime(ts) { return ts ? new Date(ts).toLocaleString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''; }
        function formatNumber(num, digits = 2) { return (num === null || typeof num === 'undefined' || isNaN(num)) ? '' : num.toFixed(digits); }

        function updateChart() {
            loader.style.display = 'block';
            chartDiv.style.display = 'none';
            tableBody.innerHTML = '';

            const params = {
                symbol: document.getElementById('symbol-select').value,
                timeframe: document.getElementById('timeframe-select').value,
                short_ema_fast: document.getElementById('short-ema-fast').value,
                short_ema_slow: document.getElementById('short-ema-slow').value,
                medium_rsi_period: document.getElementById('medium-rsi-period').value,
                long_ema_period: document.getElementById('long-ema-period').value,
                adx_period: document.getElementById('adx-period').value,
                macd_fast_period: document.getElementById('macd-fast-period').value,
                macd_slow_period: document.getElementById('macd-slow-period').value,
                macd_signal_period: document.getElementById('macd-signal-period').value,
                stoch_period: document.getElementById('stoch-period').value,
                bollinger_period: document.getElementById('bollinger-period').value,
                bollinger_devfactor: document.getElementById('bollinger-devfactor').value,
                ichimoku_tenkan_period: document.getElementById('ichimoku-tenkan-period').value,
                ichimoku_kijun_period: document.getElementById('ichimoku-kijun-period').value,
                ichimoku_senkou_b_period: document.getElementById('ichimoku-senkou-b-period').value,
                ichimoku_chikou_period: document.getElementById('ichimoku-kijun-period').value,
            };
            
            fetch(`/get_chart_data?${new URLSearchParams(params).toString()}`)
                .then(response => response.json())
                .then(data => {
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
                    chartDiv.style.display = 'block';
                    window.dispatchEvent(new Event('resize'));
                });
        }
        
        function buildTradeTable(trades) {
            tableBody.innerHTML = '';
            trades.forEach(trade => {
                const row = tableBody.insertRow();
                row.innerHTML = `
                    <td style="color:${trade['方向'] === 'BUY' ? 'red' : 'green'}">${trade['方向']}</td><td>${formatNumber(trade['数量'], 2)}</td>
                    <td>${formatNumber(trade['エントリー価格'])}</td><td>${formatDateTime(trade['エントリー日時'])}</td><td>${trade['エントリー根拠']}</td>
                    <td>${formatNumber(trade['決済価格'])}</td><td>${formatDateTime(trade['決済日時'])}</td><td>${trade['決済根拠']}</td>
                    <td>${formatNumber(trade['損益'])}</td><td>${formatNumber(trade['損益(手数料込)'])}</td><td>${formatNumber(trade['ストップロス価格'])}</td>
                    <td>${formatNumber(trade['テイクプロフィット価格'])}</td><td>${formatNumber(trade['エントリー時長期EMA'])}</td><td>${formatNumber(trade['エントリー時中期RSI'])}</td>
                    <td>${formatNumber(trade['エントリー時転換線'])}</td><td>${formatNumber(trade['エントリー時基準線'])}</td>
                    <td>${formatNumber(trade['エントリー時短期ADX'])}</td><td>${formatNumber(trade['エントリー時中期ADX'])}</td><td>${formatNumber(trade['エントリー時長期ADX'])}</td>
                `;
                row.addEventListener('click', (event) => {
                    document.querySelectorAll('#trades-table tbody tr').forEach(tr => tr.classList.remove('highlighted'));
                    event.currentTarget.classList.add('highlighted');
                    highlightTradeOnChart(trade);
                });
            });
        }

        function highlightTradeOnChart(trade) {
            const chartDataX = chartDiv.data[0].x; 
            const entryTime = new Date(trade['エントリー日時']);
            const exitTime = new Date(trade['決済日時']);
            let highlightStartTime = null, highlightEndTime = null, endIndex = -1;
            for (let i = chartDataX.length - 1; i >= 0; i--) { if (new Date(chartDataX[i]) <= entryTime) { highlightStartTime = chartDataX[i]; break; } }
            for (let i = chartDataX.length - 1; i >= 0; i--) { if (new Date(chartDataX[i]) <= exitTime) { highlightEndTime = chartDataX[i]; endIndex = i; break; } }
            if (!highlightStartTime || !highlightEndTime) return;
            let highlightVisualEndTime = (endIndex < chartDataX.length - 1) ? chartDataX[endIndex + 1] : highlightEndTime;
            const currentLayout = chartDiv.layout;
            currentLayout.shapes = (currentLayout.shapes || []).filter(s => s.name !== 'highlight-shape');
            currentLayout.shapes.push({
                name: 'highlight-shape', type: 'rect', xref: 'x', yref: 'paper', x0: highlightStartTime, y0: 0,
                x1: highlightVisualEndTime, y1: 1, fillcolor: 'rgba(255, 255, 0, 0.3)', line: { width: 0 }, layer: 'below'
            });
            Plotly.relayout('chart', { 'shapes': currentLayout.shapes });
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
    print("2. データフォルダに必要なCSVデータを配置します。")
    print("3. バックテストを実行します（分析前に必ず実行）: python run_backtrader.py")
    print("4. Webアプリケーションを起動します: python app.py")
    print("5. Webブラウザで http://127.0.0.1:5001 を開きます。")
