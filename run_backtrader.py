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
        size = abs(self.strategy.executed_size)
        
        exit_price = 0
        if size > 0:
            if trade.long: 
                exit_price = entry_price + (pnl / size)
            else: 
                exit_price = entry_price - (pnl / size)
        
        if pnl > 0:
            exit_reason = "Take Profit"
        elif pnl < 0:
            exit_reason = "Stop Loss"
        else:
            exit_reason = "Closed at entry price"
            if exit_price == 0:
                 exit_price = entry_price
        
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
            'ストップロス価格': self.strategy.sl_price, 
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

    logger.info("\n\n★★★ 全銘柄バックテストサマリー ★★★\n" + report_df.to_string())
    notifier.send_email(subject="【Backtrader】全銘柄バックテスト完了レポート", body=f"全てのバックテストが完了しました。\n\n--- サマリー ---\n{report_df.to_string()}")

if __name__ == '__main__':
    main()