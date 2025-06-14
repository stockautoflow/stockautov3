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
import report_generator

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
        return None, None, None

    data = bt.feeds.PandasData(dataname=dataframe, timeframe=bt.TimeFrame.TFrame(config.BACKTEST_CSV_BASE_TIMEFRAME_STR), compression=config.BACKTEST_CSV_BASE_COMPRESSION)
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
    
    results = cerebro.run()
    strat = results[0]
    trade_analysis = strat.analyzers.trade.get_analysis()

    # レポート用に生の数値を返す
    raw_stats = {
        'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0),
        'gross_won': trade_analysis.get('pnl', {}).get('gross', {}).get('won', 0),
        'gross_lost': trade_analysis.get('pnl', {}).get('gross', {}).get('lost', 0),
        'total_trades': trade_analysis.get('total', {}).get('total', 0),
        'win_trades': trade_analysis.get('won', {}).get('total', 0),
    }
    return raw_stats, dataframe.index[0], dataframe.index[-1]

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
    start_dates, end_dates = [], []
    for filepath in csv_files:
        stats, start_date, end_date = run_backtest_for_symbol(filepath, btrader_strategy.MultiTimeFrameStrategy)
        if stats:
            all_results.append(stats)
            start_dates.append(start_date)
            end_dates.append(end_date)

    if not all_results:
        logger.warning("有効なバックテスト結果がありませんでした。")
        return

    # 全体の開始日と終了日を取得
    overall_start = min(start_dates)
    overall_end = max(end_dates)
    
    # レポート生成
    report_df = report_generator.generate_report(all_results, strategy_params, overall_start, overall_end)

    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    summary_filename = f"summary_{timestamp}.csv"
    summary_path = os.path.join(config.REPORT_DIR, summary_filename)
    
    report_df.to_csv(summary_path, index=False, encoding='utf-8-sig')

    logger.info("\n\n★★★ 全銘柄バックテストサマリー ★★★\n" + report_df.to_string())
    logger.info(f"サマリーレポートを保存しました: {summary_path}")

    notifier.send_email(
        subject="【Backtrader】全銘柄バックテスト完了レポート",
        body=f"全てのバックテストが完了しました。\n\n--- サマリー ---\n{report_df.to_string()}"
    )

if __name__ == '__main__':
    main()
