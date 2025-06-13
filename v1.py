# ==============================================================================
# このコードブロックには、Backtrader版の全てのファイルが含まれています。
# プロジェクトディレクトリ: C:\stockautov3
# 1. requirements.txt
# 2. config_backtrader.py
# 3. strategy.yml
# 4. run_backtrader.py (メインの実行ファイル)
# 5. btrader_strategy.py (戦略定義ファイル)
# 6. notifier.py
# ==============================================================================

# ==============================================================================
# ファイル: requirements.txt
# ==============================================================================
backtrader
backtrader-plotting
pandas==2.1.4
numpy==1.26.4
PyYAML==6.0.1
matplotlib

# ==============================================================================
# ファイル: config_backtrader.py
# 説明: システム全体の設定を管理します。
# ==============================================================================
import os

# --- ディレクトリ設定 ---
# このプロジェクトのルートディレクトリ (例: C:\stockautov3)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'backtest_results')

# --- バックテスト設定 ---
INITIAL_CAPITAL = 10000000
# 基準となるCSVファイルの足種（Backtraderが認識できる形式）
# 例: 'minutes', 'daily', 'weekly', 'monthly'
BACKTEST_CSV_BASE_TIMEFRAME_STR = 'minutes'
BACKTEST_CSV_BASE_COMPRESSION = 5 # 5分足の場合

# --- メール通知設定 ---
EMAIL_CONFIG = {
    "ENABLED": True,
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": 587,
    "SMTP_USER": "your_email@gmail.com",
    "SMTP_PASSWORD": "your_app_password",
    "RECIPIENT_EMAIL": "recipient_email@example.com"
}

# ==============================================================================
# ファイル: strategy.yml
# 説明: 取引戦略のパラメータを定義します。
# ==============================================================================
strategy_name: "Multi-Timeframe EMA/RSI Strategy"

# 各時間足のパラメータ
timeframes:
  long:
    timeframe: "days"
    compression: 1
  medium:
    timeframe: "minutes"
    compression: 60
  short:
    timeframe: "minutes"
    compression: 5

# インジケーターのパラメータ
indicators:
  long_ema_period: 200
  medium_rsi_period: 14
  short_ema_fast: 10
  short_ema_slow: 25
  atr_period: 14

# フィルタリング条件
filters:
  medium_rsi_lower: 30
  medium_rsi_upper: 70

# 決済ルール
exit_rules:
  take_profit_atr_multiplier: 2.0
  stop_loss_atr_multiplier: 1.0
  
# ポジションサイジング
sizing:
  order_percentage: 0.1 # 資金の10%を1回の取引に使用

# ==============================================================================
# ファイル: notifier.py
# 説明: メール通知機能を提供します。
# ==============================================================================
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config_backtrader as config

def send_email(subject, body):
    if not config.EMAIL_CONFIG["ENABLED"]:
        return

    msg = MIMEMultipart()
    msg['From'] = config.EMAIL_CONFIG["SMTP_USER"]
    msg['To'] = config.EMAIL_CONFIG["RECIPIENT_EMAIL"]
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        print(f"メールを送信中... To: {config.EMAIL_CONFIG['RECIPIENT_EMAIL']}")
        server = smtplib.SMTP(config.EMAIL_CONFIG["SMTP_SERVER"], config.EMAIL_CONFIG["SMTP_PORT"])
        server.starttls()
        server.login(config.EMAIL_CONFIG["SMTP_USER"], config.EMAIL_CONFIG["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        print("メールを正常に送信しました。")
    except Exception as e:
        print(f"メール送信中にエラーが発生しました: {e}")

# ==============================================================================
# ファイル: btrader_strategy.py
# 説明: Backtrader用の戦略クラスを定義します。
# ==============================================================================
import backtrader as bt
import yaml

class MultiTimeFrameStrategy(bt.Strategy):
    params = (
        ('strategy_file', 'strategy.yml'),
    )

    def __init__(self):
        # 戦略ファイルを読み込む
        with open(self.p.strategy_file, 'r') as f:
            self.strategy_params = yaml.safe_load(f)

        p = self.strategy_params

        # データフィードをエイリアスでアクセスしやすくする
        self.short_data = self.datas[0]
        self.medium_data = self.datas[1]
        self.long_data = self.datas[2]

        # --- インジケーターの定義 ---
        # 長期足
        self.long_ema = bt.indicators.EMA(self.long_data.close, 
                                          period=p['indicators']['long_ema_period'])
        
        # 中期足
        self.medium_rsi = bt.indicators.RSI(self.medium_data.close, 
                                            period=p['indicators']['medium_rsi_period'])

        # 短期足
        self.short_ema_fast = bt.indicators.EMA(self.short_data.close, 
                                                period=p['indicators']['short_ema_fast'])
        self.short_ema_slow = bt.indicators.EMA(self.short_data.close, 
                                                period=p['indicators']['short_ema_slow'])
        self.short_cross = bt.indicators.CrossOver(self.short_ema_fast, self.short_ema_slow)
        self.atr = bt.indicators.ATR(self.short_data, 
                                     period=p['indicators']['atr_period'])

        # 注文追跡用
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f"BUY EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}")
            elif order.issell():
                self.log(f"SELL EXECUTED, Price: {order.executed.price:.2f}, Cost: {order.executed.value:.2f}, Comm: {order.executed.comm:.2f}")
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log(f"OPERATION PROFIT, GROSS {trade.pnl:.2f}, NET {trade.pnlcomm:.2f}")

    def next(self):
        if self.order:
            return

        if not self.position:
            # 1. 長期トレンドの確認
            long_ok = self.long_data.close[0] > self.long_ema[0]

            # 2. 中期状況の確認
            p_filters = self.strategy_params['filters']
            medium_ok = p_filters['medium_rsi_lower'] < self.medium_rsi[0] < p_filters['medium_rsi_upper']

            # 3. 短期エントリートリガー
            short_ok = self.short_cross[0] > 0

            if long_ok and medium_ok and short_ok:
                p_exit = self.strategy_params['exit_rules']
                atr_val = self.atr[0]
                
                # 利益確定と損切り価格を計算
                stop_loss_price = self.short_data.close[0] - atr_val * p_exit['stop_loss_atr_multiplier']
                take_profit_price = self.short_data.close[0] + atr_val * p_exit['take_profit_atr_multiplier']

                # ポジションサイズを計算
                p_sizing = self.strategy_params['sizing']
                cash = self.broker.get_cash()
                size = (cash * p_sizing['order_percentage']) / self.short_data.close[0]

                self.log(f"BUY CREATE, Price: {self.short_data.close[0]:.2f}, Size: {size:.2f}")
                # ブラケット注文（OCO注文）を発注
                self.order = self.buy_bracket(
                    size=size,
                    price=self.short_data.close[0],
                    limitprice=take_profit_price,
                    stopprice=stop_loss_price
                )
    
    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} - {txt}')

# ==============================================================================
# ファイル: run_backtrader.py
# 説明: Backtraderの実行、分析、プロットを行うメインファイルです。
# ==============================================================================
import backtrader as bt
import pandas as pd
import os
import glob
import yaml
from datetime import datetime
import config_backtrader as config
import btrader_strategy
import notifier

def get_csv_files(data_dir):
    """データディレクトリから銘柄ごとのCSVファイルパスを取得"""
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    return glob.glob(file_pattern)

def run_backtest_for_symbol(filepath, strategy_cls):
    """単一銘柄のバックテストを実行する"""
    symbol = os.path.basename(filepath).split('_')[0]
    print(f"\n▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    
    # 1. Cerebroエンジンを初期化
    cerebro = bt.Cerebro()

    # 2. 戦略を追加
    cerebro.addstrategy(strategy_cls)

    # 3. データフィードを追加
    data = bt.feeds.GenericCSVData(
        dataname=filepath,
        dtformat=('%Y-%m-%d %H:%M:%S'),
        datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        timeframe=bt.TimeFrame.TFrame(config.BACKTEST_CSV_BASE_TIMEFRAME_STR),
        compression=config.BACKTEST_CSV_BASE_COMPRESSION
    )
    cerebro.adddata(data)
    
    # 4. マルチタイムフレームデータをリサンプリングして追加
    with open('strategy.yml', 'r') as f:
        strategy_params = yaml.safe_load(f)

    tf_medium = strategy_params['timeframes']['medium']
    cerebro.resampledata(data, timeframe=bt.TimeFrame.TFrame(tf_medium['timeframe']), compression=tf_medium['compression'], name="medium")
    
    tf_long = strategy_params['timeframes']['long']
    cerebro.resampledata(data, timeframe=bt.TimeFrame.TFrame(tf_long['timeframe']), compression=tf_long['compression'], name="long")

    # 5. 初期資金と手数料を設定
    cerebro.broker.set_cash(config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=0.001) # 例: 0.1%

    # 6. アナライザーを追加
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addanalyzer(bt.analyzers.Sharpe, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    # 7. バックテスト実行
    results = cerebro.run()
    strat = results[0]
    
    # 8. 結果を抽出
    trade_analysis = strat.analyzers.trade.get_analysis()
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', 0)
    drawdown_info = strat.analyzers.drawdown.get_analysis()

    # 9. パフォーマンス指標を計算
    total_trades = trade_analysis.total.total if hasattr(trade_analysis.total, 'total') else 0
    win_trades = trade_analysis.won.total if hasattr(trade_analysis, 'won') else 0
    pnl_net = trade_analysis.pnl.net.total if hasattr(trade_analysis.pnl.net, 'total') else 0
    
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
    
    gross_won = trade_analysis.pnl.gross.won if hasattr(trade_analysis.pnl.gross, 'won') else 0
    gross_lost = trade_analysis.pnl.gross.lost if hasattr(trade_analysis.pnl.gross, 'lost') else 0
    profit_factor = abs(gross_won / gross_lost) if gross_lost != 0 else float('inf')
    
    max_dd = drawdown_info.max.drawdown if hasattr(drawdown_info.max, 'drawdown') else 0
    
    stats = {
        "銘柄": symbol,
        "純利益": f"{pnl_net:,.2f}",
        "勝率(%)": f"{win_rate:.2f}",
        "PF": f"{profit_factor:.2f}",
        "取引回数": total_trades,
        "最大DD(%)": f"{max_dd:.2f}",
        "シャープレシオ": f"{sharpe_ratio:.2f}"
    }

    # 10. チャートをプロットして保存
    try:
        plot_path = os.path.join(config.RESULTS_DIR, f'chart_{symbol}.png')
        print(f"チャートを保存中: {plot_path}")
        figure = cerebro.plot(style='candlestick', iplot=False)[0][0]
        figure.savefig(plot_path, dpi=300)
    except Exception as e:
        print(f"チャートのプロット中にエラーが発生しました: {e}")

    return stats

def main():
    # 実行前にディレクトリの存在を確認・作成
    # 例: C:\stockautov3\backtest_results
    if not os.path.exists(config.RESULTS_DIR):
        os.makedirs(config.RESULTS_DIR)

    csv_files = get_csv_files(config.DATA_DIR)
    if not csv_files:
        print(f"エラー: {config.DATA_DIR} に指定された形式のCSVデータが見つかりません。")
        return
        
    all_results = []
    for filepath in csv_files:
        stats = run_backtest_for_symbol(filepath, btrader_strategy.MultiTimeFrameStrategy)
        if stats:
            all_results.append(stats)

    if not all_results:
        print("有効なバックテスト結果がありませんでした。")
        return

    summary_df = pd.DataFrame(all_results).set_index('銘柄')
    summary_path = os.path.join(config.RESULTS_DIR, "summary_report.csv")
    summary_df.to_csv(summary_path)

    print("\n\n★★★ 全銘柄バックテストサマリー ★★★")
    print(summary_df.to_string())
    print(f"\nサマリーレポートを保存しました: {summary_path}")

    notifier.send_email(
        subject="【Backtrader】全銘柄バックテスト完了レポート",
        body=f"全てのバックテストが完了しました。\n\n--- サマリー ---\n{summary_df.to_string()}"
    )

if __name__ == '__main__':
    main()
