# ==============================================================================
# ファイル: create_project_files.py
# 説明: このスクリプトは、チャート生成機能を強化した株自動トレードシステムの
#       全てのファイルを生成します。
# 変更点 (v18):
#   1. chart_generator.py:
#      - エラーの原因となっていた関数のdocstringをコメントアウトに修正。
# ==============================================================================
import os

project_files = {
    "requirements.txt": """backtrader
pandas==2.1.4
numpy==1.26.4
PyYAML==6.0.1
mplfinance
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
CHART_DIR = os.path.join(RESULTS_DIR, 'chart') # チャート出力用

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
        self.short_data, self.medium_data, self.long_data = self.datas[0], self.datas[1], self.datas[2]
        self.long_ema = bt.indicators.EMA(self.long_data.close, period=p['indicators']['long_ema_period'])
        self.medium_rsi = bt.indicators.RSI(self.medium_data.close, period=p['indicators']['medium_rsi_period'])
        self.short_ema_fast = bt.indicators.EMA(self.short_data.close, period=p['indicators']['short_ema_fast'])
        self.short_ema_slow = bt.indicators.EMA(self.short_data.close, period=p['indicators']['short_ema_slow'])
        self.short_cross = bt.indicators.CrossOver(self.short_ema_fast, self.short_ema_slow)
        self.atr = bt.indicators.ATR(self.short_data, period=p['indicators']['atr_period'])
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
    
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR]:
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
import numpy as np
import mplfinance as mpf
import config_backtrader as config
import logger_setup
import logging
import yaml
import matplotlib
import matplotlib.lines as mlines
import matplotlib.pyplot as plt

matplotlib.use('Agg')
logger = logging.getLogger(__name__)

def find_latest_report(report_dir, prefix):
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_all_symbols(data_dir):
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    files = glob.glob(file_pattern)
    symbols = [os.path.basename(f).split('_')[0] for f in files]
    return sorted(list(set(symbols)))

def resample_ohlc(df, rule):
    #価格データを指定の時間足にリサンプリングする
    ohlc_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    return df.resample(rule).agg(ohlc_dict).dropna()

def plot_multi_timeframe_charts():
    logger.info("--- マルチタイムフレーム・チャート生成開始 ---")

    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    trades_df = pd.DataFrame() 
    if trade_history_path:
        logger.info(f"取引履歴ファイルを読み込みます: {trade_history_path}")
        trades_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
    else:
        logger.warning("取引履歴レポートが見つかりません。")

    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("strategy.yml が見つかりません。")
        return

    all_symbols = get_all_symbols(config.DATA_DIR)
    if not all_symbols:
        logger.error(f"{config.DATA_DIR}に価格データが見つかりません。")
        return

    p_ind = strategy_params['indicators']
    p_filter = strategy_params['filters']
    p_tf = strategy_params['timeframes']

    for symbol in all_symbols:
        try:
            logger.info(f"銘柄 {symbol} のチャートを生成中...")
            
            # --- データの準備 ---
            csv_pattern = os.path.join(config.DATA_DIR, f"{symbol}*.csv")
            data_files = glob.glob(csv_pattern)
            if not data_files:
                logger.warning(f"{symbol} の価格データが見つかりません。スキップします。")
                continue
            
            base_df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
            base_df.columns = [x.lower() for x in base_df.columns]
            
            if base_df.index.tz is not None:
                base_df.index = base_df.index.tz_localize(None)

            symbol_trades = trades_df[trades_df['銘柄'] == int(symbol)].copy() if not trades_df.empty else pd.DataFrame()

            # --- 短期チャートの描画 (5分足) ---
            df_short = base_df.copy()
            df_short['ema_fast'] = df_short['close'].ewm(span=p_ind['short_ema_fast'], adjust=False).mean()
            df_short['ema_slow'] = df_short['close'].ewm(span=p_ind['short_ema_slow'], adjust=False).mean()
            
            buy_markers = pd.Series(np.nan, index=df_short.index)
            sell_markers = pd.Series(np.nan, index=df_short.index)
            sl_lines = pd.Series(np.nan, index=df_short.index)
            tp_lines = pd.Series(np.nan, index=df_short.index)

            if not symbol_trades.empty:
                for _, trade in symbol_trades.iterrows():
                    entry_idx = df_short.index.get_indexer([trade['エントリー日時']], method='nearest')[0]
                    exit_idx = df_short.index.get_indexer([trade['決済日時']], method='nearest')[0]
                    entry_ts = df_short.index[entry_idx]
                    exit_ts = df_short.index[exit_idx]
                    
                    if trade['方向'] == 'BUY':
                        buy_markers.loc[entry_ts] = df_short['low'].iloc[entry_idx] * 0.99
                    else: # SELL
                        sell_markers.loc[entry_ts] = df_short['high'].iloc[entry_idx] * 1.01
                    sl_lines.loc[entry_ts:exit_ts] = trade['ストップロス価格']
                    tp_lines.loc[entry_ts:exit_ts] = trade['テイクプロフィット価格']
            
            short_plots = [
                mpf.make_addplot(df_short[['ema_fast', 'ema_slow']]),
                mpf.make_addplot(buy_markers, type='scatter', marker='^', color='g', markersize=100),
                mpf.make_addplot(sell_markers, type='scatter', marker='v', color='r', markersize=100),
                mpf.make_addplot(sl_lines, color='red', linestyle=':'),
                mpf.make_addplot(tp_lines, color='green', linestyle=':'),
            ]
            
            save_path_short = os.path.join(config.CHART_DIR, f'chart_short_{symbol}.png')
            mpf.plot(df_short, type='candle', style='yahoo', title=f"{symbol} Short-Term ({p_tf['short']['compression']}min)",
                     volume=True, addplot=short_plots, figsize=(20, 10),
                     savefig=dict(fname=save_path_short, dpi=100), tight_layout=True)
            logger.info(f"短期チャートを保存しました: {save_path_short}")


            # --- 中期チャートの描画 (60分足) ---
            df_medium = resample_ohlc(base_df, f"{p_tf['medium']['compression']}min")
            delta = df_medium['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
            rs = gain / loss
            df_medium['rsi'] = 100 - (100 / (1 + rs))
            
            medium_plots = [
                mpf.make_addplot(df_medium['rsi'], panel=2, color='b', ylabel='RSI'),
                mpf.make_addplot(pd.Series(p_filter['medium_rsi_upper'], index=df_medium.index), panel=2, color='r', linestyle='--'),
                mpf.make_addplot(pd.Series(p_filter['medium_rsi_lower'], index=df_medium.index), panel=2, color='g', linestyle='--')
            ]

            save_path_medium = os.path.join(config.CHART_DIR, f'chart_medium_{symbol}.png')
            mpf.plot(df_medium, type='candle', style='yahoo', title=f"{symbol} Medium-Term ({p_tf['medium']['compression']}min)",
                     volume=True, addplot=medium_plots, figsize=(20, 10), panel_ratios=(3,1,2),
                     savefig=dict(fname=save_path_medium, dpi=100), tight_layout=True)
            logger.info(f"中期チャートを保存しました: {save_path_medium}")


            # --- 長期チャートの描画 (日足) ---
            df_long = resample_ohlc(base_df, 'D')
            df_long['ema_long'] = df_long['close'].ewm(span=p_ind['long_ema_period'], adjust=False).mean()
            
            long_plots = [ mpf.make_addplot(df_long['ema_long'], color='purple') ]

            save_path_long = os.path.join(config.CHART_DIR, f'chart_long_{symbol}.png')
            mpf.plot(df_long, type='candle', style='yahoo', title=f'{symbol} Long-Term (Daily)',
                     volume=True, addplot=long_plots, figsize=(20, 10),
                     savefig=dict(fname=save_path_long, dpi=100), tight_layout=True)
            logger.info(f"長期チャートを保存しました: {save_path_long}")

        except Exception as e:
            logger.error(f"銘柄 {symbol} のチャート生成中にエラーが発生しました。", exc_info=True)

    logger.info("--- 全てのチャート生成が完了しました ---")

def main():
    logger_setup.setup_logging()
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    plot_multi_timeframe_charts()

if __name__ == '__main__':
    main()
"""
}

def create_files(files_dict):
    """
    辞書を受け取り、ファイル名と内容でファイルを作成する関数
    """
    for filename, content in files_dict.items():
        # ファイルの内容の先頭にある可能性のある空行を削除
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
    print("次に、仮想環境をセットアップし、ライブラリをインストールしてください。")
