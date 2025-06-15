# ==============================================================================
# ファイル: create_project_files.py
# 説明: このスクリプトを実行すると、株自動トレードシステムに必要な
#       全てのファイルがカレントディレクトリに生成されます。
# 使い方: 
#   1. このファイル (create_project_files.py) を C:\stockautov3 に保存します。
#   2. コマンドプロンプトで C:\stockautov3 に移動し、'python create_project_files.py' を実行します。
# ==============================================================================
import os

# プロジェクトの全ファイルを辞書として定義
# キー: ファイル名, 値: ファイルの内容
project_files = {
    "requirements.txt": """backtrader
pandas==2.1.4
numpy==1.26.4
PyYAML==6.0.1
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

# --- バックテスト設定 ---
INITIAL_CAPITAL = 70000000
BACKTEST_CSV_BASE_TIMEFRAME_STR = 'Minutes' 
BACKTEST_CSV_BASE_COMPRESSION = 5
COMMISSION_PERC = 0.0005 # 0.05%
SLIPPAGE_PERC = 0.0002 # 0.02%

# --- ロギング設定 ---
LOG_LEVEL = logging.INFO # INFO or DEBUG
""",

    "strategy.yml": """strategy_name: "Multi-Timeframe EMA/RSI Strategy"
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
        long_ok = self.long_data.close[0] > self.long_ema[0]
        filters = p['filters']
        medium_ok = filters['medium_rsi_lower'] < self.medium_rsi[0] < filters['medium_rsi_upper']
        short_ok = self.short_cross[0] > 0

        if long_ok and medium_ok and short_ok:
            exit_rules = p['exit_rules']
            atr_val = self.atr[0]
            if atr_val == 0: return

            stop_loss = self.short_data.close[0] - atr_val * exit_rules['stop_loss_atr_multiplier']
            take_profit = self.short_data.close[0] + atr_val * exit_rules['take_profit_atr_multiplier']
            
            sizing_params = p['sizing']
            cash = self.broker.get_cash()
            risk_per_share = atr_val * exit_rules['stop_loss_atr_multiplier']
            allowed_risk_amount = cash * sizing_params['risk_per_trade']
            size = allowed_risk_amount / risk_per_share if risk_per_share > 0 else 0

            self.entry_reason = f"L:C>EMA({p['indicators']['long_ema_period']}), M:RSI({p['indicators']['medium_rsi_period']})={self.medium_rsi[0]:.1f}, S:Cross"
            
            self.log(f"BUY CREATE, Price: {self.short_data.close[0]:.2f}, Size: {size:.2f}, Reason: {self.entry_reason}")
            self.order = self.buy_bracket(size=size, price=self.short_data.close[0], limitprice=take_profit, stopprice=stop_loss)
    
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
    env_logic_desc = f"長期足({format_tf(p['timeframes']['long'])})の終値 > EMA({p['indicators']['long_ema_period']})"
    entry_signal_desc = f"短期足EMA({p['indicators']['short_ema_fast']})がEMA({p['indicators']['short_ema_slow']})をクロス & 中期足RSI({p['indicators']['medium_rsi_period']})が{p['filters']['medium_rsi_lower']}~{p['filters']['medium_rsi_upper']}の範囲"
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

# 取引の詳細を記録するためのアナライザー
class TradeList(bt.Analyzer):
    def __init__(self):
        self.trades = []
        self.symbol = self.strategy.data._name
        self.entry_reasons = {}

    def notify_trade(self, trade):
        if trade.isopen:
            # トレード開始時にエントリー根拠を保存
            self.entry_reasons[trade.ref] = self.strategy.entry_reason
            return

        if trade.isclosed:
            # ★★★ 修正点: 決済理由を動的に生成 ★★★
            p = self.strategy.strategy_params
            exit_rules = p['exit_rules']
            
            if trade.pnl >= 0:
                exit_reason = f"Take Profit (ATR x{exit_rules['take_profit_atr_multiplier']})"
            else:
                exit_reason = f"Stop Loss (ATR x{exit_rules['stop_loss_atr_multiplier']})"
            
            # 決済時の価格計算
            exit_price = 0
            if self.strategy.trade_size: 
                exit_price = trade.price + (trade.pnl / self.strategy.trade_size)

            self.trades.append({
                '銘柄': self.symbol,
                '方向': 'BUY' if trade.long else 'SELL',
                '数量': self.strategy.trade_size,
                'エントリー価格': trade.price,
                'エントリー日時': bt.num2date(trade.dtopen).isoformat(),
                'エントリー根拠': self.entry_reasons.pop(trade.ref, "N/A"),
                '決済価格': exit_price,
                '決済日時': bt.num2date(trade.dtclose).isoformat(),
                '決済根拠': exit_reason,
                '損益': trade.pnl,
                '損益(手数料込)': trade.pnlcomm,
            })

    def get_analysis(self):
        return self.trades

def get_csv_files(data_dir):
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    return glob.glob(file_pattern)

def run_backtest_for_symbol(filepath, strategy_cls):
    symbol = os.path.basename(filepath).split('_')[0]
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    
    cerebro = bt.Cerebro()
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
    start_dates, end_dates = [], []
    for filepath in csv_files:
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(filepath, btrader_strategy.MultiTimeFrameStrategy)
        if stats:
            all_results.append(stats)
            all_trades.extend(trade_list)
            start_dates.append(start_date)
            end_dates.append(end_date)

    if not all_results:
        logger.warning("有効なバックテスト結果がありませんでした。")
        return

    overall_start = min(start_dates)
    overall_end = max(end_dates)
    
    report_df = report_generator.generate_report(all_results, strategy_params, overall_start, overall_end)

    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    summary_filename = f"summary_{timestamp}.csv"
    summary_path = os.path.join(config.REPORT_DIR, summary_filename)
    report_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
    logger.info(f"サマリーレポートを保存しました: {summary_path}")

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

