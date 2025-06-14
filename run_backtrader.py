import backtrader as bt
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

logger = logging.getLogger(__name__)

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
        return None

    data = bt.feeds.PandasData(dataname=dataframe, timeframe=bt.TimeFrame.TFrame(config.BACKTEST_CSV_BASE_TIMEFRAME_STR), compression=config.BACKTEST_CSV_BASE_COMPRESSION)
    cerebro.adddata(data)
    
    with open('strategy.yml', 'r', encoding='utf-8') as f:
        strategy_params = yaml.safe_load(f)

    tf_medium = strategy_params['timeframes']['medium']
    cerebro.resampledata(data, timeframe=bt.TimeFrame.TFrame(tf_medium['timeframe']), compression=tf_medium['compression'], name="medium")
    tf_long = strategy_params['timeframes']['long']
    cerebro.resampledata(data, timeframe=bt.TimeFrame.TFrame(tf_long['timeframe']), compression=tf_long['compression'], name="long")

    cerebro.broker.set_cash(config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    results = cerebro.run()
    strat = results[0]
    
    trade_analysis = strat.analyzers.trade.get_analysis()
    sharpe_analysis = strat.analyzers.sharpe.get_analysis()
    drawdown_info = strat.analyzers.drawdown.get_analysis()

    total_trades = trade_analysis.get('total', {}).get('total', 0)
    win_trades = trade_analysis.get('won', {}).get('total', 0)
    pnl_net = trade_analysis.get('pnl', {}).get('net', {}).get('total', 0)
    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
    gross_won = trade_analysis.get('pnl', {}).get('gross', {}).get('won', 0)
    gross_lost = trade_analysis.get('pnl', {}).get('gross', {}).get('lost', 0)
    profit_factor = abs(gross_won / gross_lost) if gross_lost != 0 else float('inf')
    max_dd = drawdown_info.get('max', {}).get('drawdown', 0)
    sharpe_ratio = sharpe_analysis.get('sharperatio')
    sharpe_ratio_str = f"{sharpe_ratio:.2f}" if sharpe_ratio is not None else "N/A"
    
    stats = {"銘柄": symbol, "純利益": f"{pnl_net:,.2f}", "勝率(%)": f"{win_rate:.2f}", "PF": f"{profit_factor:.2f}", "取引回数": total_trades, "最大DD(%)": f"{max_dd:.2f}", "シャープレシオ": sharpe_ratio_str}

    return stats

def main():
    logger_setup.setup_logging()
    logger.info("--- 全銘柄バックテスト開始 ---")
    
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    csv_files = get_csv_files(config.DATA_DIR)
    if not csv_files:
        logger.error(f"{config.DATA_DIR} に指定された形式のCSVデータが見つかりません。")
        return
        
    all_results = []
    for filepath in csv_files:
        stats = run_backtest_for_symbol(filepath, btrader_strategy.MultiTimeFrameStrategy)
        if stats:
            all_results.append(stats)

    if not all_results:
        logger.warning("有効なバックテスト結果がありませんでした。")
        return

    summary_df = pd.DataFrame(all_results).set_index('銘柄')
    
    # ★★★ 修正点: タイムスタンプ付きのファイル名を生成 ★★★
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    summary_filename = f"summary_{timestamp}.csv"
    summary_path = os.path.join(config.REPORT_DIR, summary_filename)
    
    summary_df.to_csv(summary_path)

    logger.info("\n\n★★★ 全銘柄バックテストサマリー ★★★\n" + summary_df.to_string())
    logger.info(f"サマリーレポートを保存しました: {summary_path}")

    notifier.send_email(
        subject="【Backtrader】全銘柄バックテスト完了レポート",
        body=f"全てのバックテストが完了しました。\n\n--- サマリー ---\n{summary_df.to_string()}"
    )

if __name__ == '__main__':
    main()
