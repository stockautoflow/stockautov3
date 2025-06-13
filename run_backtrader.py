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
    try:
        dataframe = pd.read_csv(
            filepath,
            index_col='datetime',
            parse_dates=True,
            encoding='utf-8-sig' # BOM付きUTF-8に対応
        )
        # カラム名を小文字に統一
        dataframe.columns = [x.lower() for x in dataframe.columns]
    except Exception as e:
        print(f"CSVファイルの読み込みに失敗しました: {filepath} - {e}")
        return None

    data = bt.feeds.PandasData(
        dataname=dataframe,
        timeframe=bt.TimeFrame.TFrame(config.BACKTEST_CSV_BASE_TIMEFRAME_STR),
        compression=config.BACKTEST_CSV_BASE_COMPRESSION
    )
    cerebro.adddata(data)
    
    # 4. マルチタイムフレームデータをリサンプリングして追加
    with open('strategy.yml', 'r', encoding='utf-8') as f:
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
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    # 7. バックテスト実行
    results = cerebro.run()
    strat = results[0]
    
    # 8. 結果を抽出
    trade_analysis = strat.analyzers.trade.get_analysis()
    sharpe_analysis = strat.analyzers.sharpe.get_analysis()
    drawdown_info = strat.analyzers.drawdown.get_analysis()

    # 9. パフォーマンス指標を計算
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    win_trades = trade_analysis.get('won', {}).get('total', 0)
    pnl_net = trade_analysis.get('pnl', {}).get('net', {}).get('total', 0)
    
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
    
    gross_won = trade_analysis.get('pnl', {}).get('gross', {}).get('won', 0)
    gross_lost = trade_analysis.get('pnl', {}).get('gross', {}).get('lost', 0)
    profit_factor = abs(gross_won / gross_lost) if gross_lost != 0 else float('inf')
    
    max_dd = drawdown_info.get('max', {}).get('drawdown', 0)
    
    # ★★★ 修正点: sharpe_ratioがNoneの場合の処理を追加 ★★★
    sharpe_ratio = sharpe_analysis.get('sharperatio')
    sharpe_ratio_str = f"{sharpe_ratio:.2f}" if sharpe_ratio is not None else "N/A"
    
    stats = {
        "銘柄": symbol,
        "純利益": f"{pnl_net:,.2f}",
        "勝率(%)": f"{win_rate:.2f}",
        "PF": f"{profit_factor:.2f}",
        "取引回数": total_trades,
        "最大DD(%)": f"{max_dd:.2f}",
        "シャープレシオ": sharpe_ratio_str
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
