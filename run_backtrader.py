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
    def __init__(self): self.trades, self.symbol = [], ""
    def start(self): self.symbol = self.strategy.data._name
    def notify_trade(self, trade):
        if not trade.isclosed: return
        size, pnl = abs(getattr(trade, 'executed_size', 0)), trade.pnl
        exit_price = (trade.value + pnl) / size if size > 0 else trade.price
        self.trades.append({'銘柄': self.symbol, '方向': 'BUY' if trade.long else 'SELL', '数量': size,
                            'エントリー価格': trade.price, 'エントリー日時': bt.num2date(trade.dtopen).replace(tzinfo=None).isoformat(), 'エントリー根拠': getattr(trade, 'entry_reason_for_trade', 'N/A'),
                            '決済価格': exit_price, '決済日時': bt.num2date(trade.dtclose).replace(tzinfo=None).isoformat(), '決済根拠': "Take Profit" if trade.pnlcomm >= 0 else "Stop Loss",
                            '損益': trade.pnl, '損益(手数料込)': trade.pnlcomm, 'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price})
    def stop(self):
        if not self.strategy.position: return
        pos, entry_price, size = self.strategy.position, self.strategy.position.price, self.strategy.position.size
        exit_price, pnl = self.strategy.data.close[0], (self.strategy.data.close[0] - entry_price) * size
        commission = (abs(size)*entry_price*config.COMMISSION_PERC) + (abs(size)*exit_price*config.COMMISSION_PERC)
        self.trades.append({'銘柄': self.symbol, '方向': 'BUY' if size > 0 else 'SELL', '数量': abs(size),
                            'エントリー価格': entry_price, 'エントリー日時': self.strategy.current_position_entry_dt.isoformat(), 'エントリー根拠': self.strategy.entry_reason,
                            '決済価格': exit_price, '決済日時': self.strategy.data.datetime.datetime(0).isoformat(), '決済根拠': "End of Backtest",
                            '損益': pnl, '損益(手数料込)': pnl - commission, 'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price})
    def get_analysis(self): return self.trades

def load_data_feed(filepath, timeframe_str, compression):
    try:
        df = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        df.columns = [x.lower() for x in df.columns]
        return bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.TFrame(timeframe_str), compression=compression)
    except Exception as e:
        logger.error(f"CSV読み込みまたはデータフィード作成で失敗: {filepath} - {e}")
        return None

def run_backtest_for_symbol(symbol, base_filepath, strategy_cls, strategy_params):
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(strategy_cls, strategy_params=strategy_params)
    
    timeframes_config = strategy_params['timeframes']
    data_feeds = {}
    
    short_tf = timeframes_config['short']
    base_data = load_data_feed(base_filepath, short_tf['timeframe'], short_tf['compression'])
    if base_data is None: return None, None, None, None
    base_data._name = symbol
    data_feeds['short'] = base_data

    for tf_name in ['medium', 'long']:
        tf_config = timeframes_config[tf_name]
        source_type = tf_config.get('source_type', 'resample')

        if source_type == 'direct':
            pattern_template = tf_config.get('file_pattern')
            if not pattern_template:
                logger.error(f"[{symbol}] {tf_name}のsource_typeが'direct'ですが、file_patternが未定義です。")
                return None, None, None, None
            
            search_pattern = os.path.join(config.DATA_DIR, pattern_template.format(symbol=symbol))
            data_files = glob.glob(search_pattern)
            if not data_files:
                logger.error(f"[{symbol}] {tf_name}用のデータファイルが見つかりません: {search_pattern}")
                return None, None, None, None
            
            data_feed = load_data_feed(data_files[0], tf_config['timeframe'], tf_config['compression'])
            if data_feed is None: return None, None, None, None
            data_feeds[tf_name] = data_feed
        
        elif source_type == 'resample':
            data_feeds[tf_name] = {'resample': True, 'config': tf_config}

    cerebro.adddata(data_feeds['short'])
    for tf_name in ['medium', 'long']:
        feed = data_feeds[tf_name]
        if isinstance(feed, dict) and feed.get('resample'):
            cfg = feed['config']
            cerebro.resampledata(data_feeds['short'], timeframe=bt.TimeFrame.TFrame(cfg['timeframe']), compression=cfg['compression'], name=tf_name)
        else:
            cerebro.adddata(feed, name=tf_name)
    
    cerebro.broker.set_cash(config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=config.COMMISSION_PERC)
    cerebro.broker.set_slippage_perc(perc=config.SLIPPAGE_PERC)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addanalyzer(TradeList, _name='tradelist')

    # --- [変更] ZeroDivisionErrorを捕捉する例外処理を追加 ---
    try:
        results = cerebro.run()
        strat = results[0]
        trade_analysis = strat.analyzers.trade.get_analysis()
        trade_list = strat.analyzers.tradelist.get_analysis()
    
        return {'symbol': symbol, 'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0),
                'gross_won': trade_analysis.get('won', {}).get('pnl', {}).get('total', 0),
                'gross_lost': trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0),
                'total_trades': trade_analysis.get('total', {}).get('total', 0),
                'win_trades': trade_analysis.get('won', {}).get('total', 0)
               }, pd.to_datetime(strat.data.datetime.date(0)), pd.to_datetime(strat.data.datetime.date(-1)), trade_list
    except ZeroDivisionError:
        logger.warning(f"銘柄 {symbol} のバックテスト中にゼロ除算エラーが発生しました。計算不能なデータが含まれている可能性があるため、この銘柄のテストをスキップします。")
        return None, None, None, None
    # -----------------------------------------------------------

def main():
    logger_setup.setup_logging()
    logger.info("--- 全銘柄バックテスト開始 ---")
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path): os.makedirs(dir_path)
        
    with open('strategy.yml', 'r', encoding='utf-8') as f: strategy_params = yaml.safe_load(f)

    short_tf_compression = strategy_params['timeframes']['short']['compression']
    base_file_pattern = f"*_{short_tf_compression}m_*.csv"
    base_csv_files = glob.glob(os.path.join(config.DATA_DIR, base_file_pattern))
    
    if not base_csv_files:
        logger.error(f"{config.DATA_DIR}にベースデータが見つかりません (パターン: {base_file_pattern})。"); return

    all_results, all_trades, all_details, start_dates, end_dates = [], [], [], [], []
    for filepath in sorted(base_csv_files):
        symbol = os.path.basename(filepath).split('_')[0]
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(symbol, filepath, btrader_strategy.DynamicStrategy, strategy_params)
        if stats:
            all_results.append(stats)
            all_trades.extend(trade_list)
            if start_date: start_dates.append(start_date)
            if end_date: end_dates.append(end_date)
            
            win_trades = stats['win_trades']
            total_trades = stats['total_trades']
            lost_trades = total_trades - win_trades
            
            win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
            pf = abs(stats['gross_won'] / stats['gross_lost']) if stats['gross_lost'] != 0 else float('inf')
            avg_win = stats['gross_won'] / win_trades if win_trades > 0 else 0
            avg_loss = stats['gross_lost'] / lost_trades if lost_trades > 0 else 0
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            
            all_details.append({
                "銘柄": stats['symbol'],
                "純利益": f"¥{stats['pnl_net']:,.2f}",
                "総利益": f"¥{stats['gross_won']:,.2f}",
                "総損失": f"¥{stats['gross_lost']:,.2f}",
                "PF": f"{pf:.2f}",
                "勝率": f"{win_rate:.2f}%",
                "総トレード数": total_trades,
                "勝トレード": win_trades,
                "負トレード": lost_trades,
                "平均利益": f"¥{avg_win:,.2f}",
                "平均損失": f"¥{avg_loss:,.2f}",
                "RR比": f"{rr:.2f}"
            })

    if not all_results or not start_dates or not end_dates:
        logger.warning("有効な結果/期間がなくレポート生成をスキップします。"); return

    report_df = report_generator.generate_report(all_results, strategy_params, min(start_dates), max(end_dates))
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    report_df.to_csv(os.path.join(config.REPORT_DIR, f"summary_{timestamp}.csv"), index=False, encoding='utf-8-sig')
    
    if all_details: 
        pd.DataFrame(all_details).to_csv(
            os.path.join(config.REPORT_DIR, f"detail_{timestamp}.csv"), 
            index=False, 
            encoding='utf-8-sig'
        )
        
    if all_trades: 
        pd.DataFrame(all_trades).to_csv(
            os.path.join(config.REPORT_DIR, f"trade_history_{timestamp}.csv"), 
            index=False, 
            encoding='utf-8-sig'
        )

    logger.info("\n\n★★★ 全銘柄バックテストサマリー ★★★\n" + report_df.to_string())
    notifier.send_email(subject="【Backtrader】全銘柄バックテスト完了レポート", body=f"バックテストが完了しました。\n\n--- サマリー ---\n{report_df.to_string()}")

if __name__ == '__main__':
    main()