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
        if not trade.isclosed: return
        size = abs(getattr(trade, 'executed_size', 0))
        pnl = trade.pnl
        exit_price = (trade.value + pnl) / size if trade.long else (trade.value - pnl) / size if size > 0 else trade.price
        self.trades.append({
            '銘柄': self.symbol, '方向': 'BUY' if trade.long else 'SELL',
            '数量': size, 'エントリー価格': trade.price,
            'エントリー日時': bt.num2date(trade.dtopen).replace(tzinfo=None).isoformat(),
            'エントリー根拠': getattr(trade, 'entry_reason_for_trade', 'N/A'),
            '決済価格': exit_price,
            '決済日時': bt.num2date(trade.dtclose).replace(tzinfo=None).isoformat(),
            '決済根拠': "Take Profit" if trade.pnlcomm >= 0 else "Stop Loss",
            '損益': trade.pnl, '損益(手数料込)': trade.pnlcomm,
            'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price
        })
    def stop(self):
        if self.strategy.position:
            pos, broker = self.strategy.position, self.strategy.broker
            entry_price, exit_price, size = pos.price, self.strategy.data.close[0], pos.size
            pnl = (exit_price - entry_price) * size
            commission = (abs(size) * entry_price * config.COMMISSION_PERC) + (abs(size) * exit_price * config.COMMISSION_PERC)
            entry_dt = self.strategy.current_position_entry_dt.isoformat() if self.strategy.current_position_entry_dt else 'N/A'
            self.trades.append({
                '銘柄': self.symbol, '方向': 'BUY' if size > 0 else 'SELL', '数量': abs(size),
                'エントリー価格': entry_price, 'エントリー日時': entry_dt, 'エントリー根拠': self.strategy.entry_reason,
                '決済価格': exit_price, '決済日時': self.strategy.data.datetime.datetime(0).isoformat(), '決済根拠': "End of Backtest",
                '損益': pnl, '損益(手数料込)': pnl - commission,
                'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price
            })
    def get_analysis(self): return self.trades

def get_csv_files(data_dir):
    return glob.glob(os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv"))

def run_backtest_for_symbol(filepath, strategy_cls, strategy_params):
    symbol = os.path.basename(filepath).split('_')[0]
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(strategy_cls, strategy_params=strategy_params)
    try:
        dataframe = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        dataframe.columns = [x.lower() for x in dataframe.columns]
    except Exception as e:
        logger.error(f"CSV読み込みまたはVWAP計算で失敗: {filepath} - {e}"); return None, None, None, None

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

    pnl_net = trade_analysis.get('pnl', {}).get('net', {}).get('total', 0)
    won_pnl = trade_analysis.get('won', {}).get('pnl', {}).get('total', 0)
    lost_pnl = trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0)
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    win_trades = trade_analysis.get('won', {}).get('total', 0)
    
    raw_stats = {'symbol': symbol, 'pnl_net': pnl_net, 'gross_won': won_pnl, 'gross_lost': lost_pnl, 'total_trades': total_trades, 'win_trades': win_trades}
    return raw_stats, dataframe.index[0], dataframe.index[-1], trade_list

def main():
    logger_setup.setup_logging()
    logger.info("--- 全銘柄バックテスト開始 ---")
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path): os.makedirs(dir_path)
    with open('strategy.yml', 'r', encoding='utf-8') as f:
        strategy_params = yaml.safe_load(f)

    csv_files = get_csv_files(config.DATA_DIR)
    if not csv_files: logger.error(f"{config.DATA_DIR} にデータが見つかりません。"); return

    all_results, all_trades, all_details, start_dates, end_dates = [], [], [], [], []
    for filepath in csv_files:
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(filepath, btrader_strategy.DynamicStrategy, strategy_params)
        if stats:
            all_results.append(stats)
            all_trades.extend(trade_list)
            if start_date is not None: start_dates.append(start_date)
            if end_date is not None: end_dates.append(end_date)

            win_rate = (stats['win_trades'] / stats['total_trades']) * 100 if stats['total_trades'] > 0 else 0
            pf = abs(stats['gross_won'] / stats['gross_lost']) if stats['gross_lost'] != 0 else float('inf')
            avg_win = stats['gross_won'] / stats['win_trades'] if stats['win_trades'] > 0 else 0
            avg_loss = stats['gross_lost'] / (stats['total_trades'] - stats['win_trades']) if (stats['total_trades'] - stats['win_trades']) > 0 else 0
            rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            all_details.append({"銘柄": stats['symbol'], "純利益": f"¥{stats['pnl_net']:,.2f}", "PF": f"{pf:.2f}", "勝率": f"{win_rate:.2f}%", "総トレード数": stats['total_trades'], "RR比": f"{rr_ratio:.2f}"})

    if not all_results or not start_dates or not end_dates:
        logger.warning("有効な結果/期間がなくレポート生成をスキップします。"); return

    report_df = report_generator.generate_report(all_results, strategy_params, min(start_dates), max(end_dates))
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    report_df.to_csv(os.path.join(config.REPORT_DIR, f"summary_{timestamp}.csv"), index=False, encoding='utf-8-sig')
    if all_details: pd.DataFrame(all_details).set_index('銘柄').to_csv(os.path.join(config.REPORT_DIR, f"detail_{timestamp}.csv"), encoding='utf-8-sig')
    if all_trades: pd.DataFrame(all_trades).to_csv(os.path.join(config.REPORT_DIR, f"trade_history_{timestamp}.csv"), index=False, encoding='utf-8-sig')

    logger.info("\n\n★★★ 全銘柄バックテストサマリー ★★★\n" + report_df.to_string())
    notifier.send_email(subject="【Backtrader】全銘柄バックテスト完了レポート", body=f"バックテストが完了しました。\n\n--- サマリー ---\n{report_df.to_string()}")

if __name__ == '__main__':
    main()