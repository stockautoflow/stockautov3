import backtrader as bt
import pandas as pd
import os
import glob
import yaml
import logging
from datetime import datetime

from src.core.util import logger as logger_setup
from src.core.data_preparer import prepare_historical_data_feeds
from . import config_backtest as config
from . import report as report_generator
from .strategy import BacktestStrategy # <-- [修正] 新しいストラテジーをインポート

logger = logging.getLogger(__name__)

class TradeList(bt.Analyzer):
    # (TradeListアナライザークラスの実装は変更なし)
    def __init__(self): self.trades = []; self.symbol = ""; self.open_trades = {}
    def start(self): self.symbol = self.strategy.data0._name
    def notify_trade(self, trade):
        if trade.isopen:
            esg = self.strategy.exit_signal_generator
            self.open_trades[trade.ref] = {'tp_price': esg.tp_price, 'sl_price': esg.sl_price, 'risk_per_share': esg.risk_per_share, 'entry_reason': self.strategy.event_handler.current_entry_reason}
            return
        if not trade.isclosed: return
        entry_info = self.open_trades.pop(trade.ref, {})
        tp_price, sl_price, risk_per_share, entry_reason = entry_info.get('tp_price', 0.0), entry_info.get('sl_price', 0.0), entry_info.get('risk_per_share', 0.0), entry_info.get('entry_reason', 'N/A')
        profit_delta, size, pnl = abs(tp_price - trade.price) if tp_price > 0 else 0.0, abs(getattr(trade, 'executed_size', trade.size)), trade.pnl
        per_share_pnl, actual_exit_price = (pnl / size if size > 0 else 0.0), trade.price + (pnl / size if size > 0 else 0.0)
        self.trades.append({'銘柄': self.symbol, '方向': 'BUY' if trade.long else 'SELL', '数量': size, 'エントリー価格': trade.price, 'エントリー日時': bt.num2date(trade.dtopen).replace(tzinfo=None).isoformat(), 'エントリー根拠': entry_reason, '決済価格': actual_exit_price, '決済日時': bt.num2date(trade.dtclose).replace(tzinfo=None).isoformat(), '決済根拠': "Take Profit" if trade.pnlcomm >= 0 else "Stop Loss", '一株当たり損益': per_share_pnl, '損益': pnl, '損益(手数料込)': trade.pnlcomm, 'ストップロス価格': sl_price, 'テイクプロフィット価格': tp_price, '許容損失幅': risk_per_share, '目標利益幅': profit_delta})
    def stop(self):
        if not self.strategy.position: return
        pos = self.strategy.position; entry_price, size = pos.price, pos.size; exit_price = self.strategy.data0.close[0]; pnl = (exit_price - entry_price) * size
        commission = (abs(size) * entry_price * config.COMMISSION_PERC) + (abs(size) * exit_price * config.COMMISSION_PERC); per_share_pnl = (exit_price - entry_price) * (1 if size > 0 else -1)
        esg = self.strategy.exit_signal_generator; profit_delta = abs(esg.tp_price - entry_price) if esg.tp_price > 0 else 0.0
        self.trades.append({'銘柄': self.symbol, '方向': 'BUY' if size > 0 else 'SELL', '数量': abs(size), 'エントリー価格': entry_price, 'エントリー日時': self.strategy.position_manager.current_position_entry_dt.isoformat(), 'エントリー根拠': self.strategy.event_handler.current_entry_reason, '決済価格': exit_price, '決済日時': self.strategy.data0.datetime.datetime(0).isoformat(), '決済根拠': "End of Backtest", '一株当たり損益': per_share_pnl, '損益': pnl, '損益(手数料込)': pnl - commission, 'ストップロス価格': esg.sl_price, 'テイクプロフィット価格': esg.tp_price, '許容損失幅': esg.risk_per_share, '目標利益幅': profit_delta})
    def get_analysis(self): return self.trades

def run_backtest_for_symbol(symbol, base_filepath, strategy_params):
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    df_for_dates = pd.read_csv(base_filepath, index_col='datetime', parse_dates=True)
    start_date, end_date = df_for_dates.index[0], df_for_dates.index[-1]
    
    cerebro = bt.Cerebro(stdstats=False)
    
    # [修正] 履歴データ準備用の関数を呼び出し
    success = prepare_historical_data_feeds(cerebro, strategy_params, symbol, config.DATA_DIR, backtest_base_filepath=base_filepath)
    if not success:
        logger.error(f"[{symbol}] のデータフィード準備に失敗。")
        return None, None, None, None
    
    # [修正] 新しいBacktestStrategyと空のコンポーネント辞書を渡す
    strategy_components = {} 
    cerebro.addstrategy(
        BacktestStrategy,
        strategy_params=strategy_params,
        strategy_components=strategy_components
    )

    cerebro.broker.set_cash(config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=config.COMMISSION_PERC)
    cerebro.broker.set_slippage_perc(perc=config.SLIPPAGE_PERC)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addanalyzer(TradeList, _name='tradelist')

    results = cerebro.run()
    strat = results[0]
    trade_analysis = strat.analyzers.trade.get_analysis()
    trade_list = strat.analyzers.tradelist.get_analysis()
    return {
        'symbol': symbol, 'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0),
        'gross_won': trade_analysis.get('won', {}).get('pnl', {}).get('total', 0),
        'gross_lost': trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0),
        'total_trades': trade_analysis.get('total', {}).get('total', 0),
        'win_trades': trade_analysis.get('won', {}).get('total', 0)
    }, start_date, end_date, trade_list

def main():
    try:
        logger_setup.setup_logging(config.LOG_DIR, log_prefix='backtest', level=config.LOG_LEVEL)
        logger.info("--- 単一戦略バックテスト開始 ---")
        for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR]:
            if not os.path.exists(dir_path): os.makedirs(dir_path)
        strategy_file_path = os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml')
        with open(strategy_file_path, 'r', encoding='utf-8') as f: strategy_params = yaml.safe_load(f)
        short_tf_compression = strategy_params['timeframes']['short']['compression']
        base_file_pattern = f"*_{short_tf_compression}m_*.csv"
        base_csv_files = glob.glob(os.path.join(config.DATA_DIR, base_file_pattern))
        if not base_csv_files: logger.error(f"{config.DATA_DIR}にベースデータが見つかりません。"); return
        all_results, all_trades, all_details, start_dates, end_dates = [], [], [], [], []
        for filepath in sorted(base_csv_files):
            symbol = os.path.basename(filepath).split('_')[0]
            stats, start_date, end_date, trade_list = run_backtest_for_symbol(symbol, filepath, strategy_params)
            detail_data = {"銘柄": symbol, "純利益": "¥0.00", "総利益": "¥0.00", "総損失": "¥0.00", "PF": "0.00", "勝率": "0.00%", "総トレード数": 0, "勝トレード": 0, "負トレード": 0, "平均利益": "¥0.00", "平均損失": "¥0.00", "RR比": "0.00"}
            if stats:
                all_results.append(stats);
                if trade_list: all_trades.extend(trade_list)
                if start_date: start_dates.append(start_date)
                if end_date: end_dates.append(end_date)
                win_trades, total_trades = stats['win_trades'], stats['total_trades']; lost_trades = total_trades - win_trades
                win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
                pf = abs(stats['gross_won'] / stats['gross_lost']) if stats['gross_lost'] != 0 else float('inf')
                avg_win = stats['gross_won'] / win_trades if win_trades > 0 else 0
                avg_loss = stats['gross_lost'] / lost_trades if lost_trades > 0 else 0
                rr = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
                detail_data.update({"純利益": f"¥{stats['pnl_net']:,.2f}", "総利益": f"¥{stats['gross_won']:,.2f}", "総損失": f"¥{stats['gross_lost']:,.2f}", "PF": f"{pf:.2f}", "勝率": f"{win_rate:.2f}%", "総トレード数": total_trades, "勝トレード": win_trades, "負トレード": lost_trades, "平均利益": f"¥{avg_win:,.2f}", "平均損失": f"¥{avg_loss:,.2f}", "RR比": f"{rr:.2f}"})
            all_details.append(detail_data)
        timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
        pd.DataFrame(all_details).to_csv(os.path.join(config.RESULTS_DIR, f"detail_{timestamp}.csv"), index=False, encoding='utf-8-sig')
        logger.info(f"詳細レポートを detail_{timestamp}.csv に保存しました。")

        if start_dates and end_dates:
            report_df = report_generator.generate_report(all_results, strategy_params, min(start_dates), max(end_dates))
            report_df.to_csv(os.path.join(config.RESULTS_DIR, f"summary_{timestamp}.csv"), index=False, encoding='utf-8-sig')
            logger.info(f"サマリーレポートを summary_{timestamp}.csv に保存しました。")
            logger.info("\n\n★★★ 全銘柄バックテストサマリー ★★★\n" + report_df.to_string())

        else:
            logger.warning("バックテスト対象期間を特定できなかったため、サマリーレポートは生成されませんでした。")

        logger.info("取引履歴(trade_history.csv)の保存処理を開始...")

        TRADE_HISTORY_COLUMNS = [
            '銘柄', '方向', '数量', 'エントリー価格', 'エントリー日時', 'エントリー根拠',
            '決済価格', '決済日時', '決済根拠',
            '一株当たり損益', '損益', '損益(手数料込)',
            'ストップロス価格', 'テイクプロフィット価格',
            '許容損失幅', '目標利益幅'
        ]

        if not all_trades:
            logger.info("取引履歴が0件のため、ヘッダーのみのファイルを生成します。")
            trade_history_df = pd.DataFrame(columns=TRADE_HISTORY_COLUMNS)
        else:
            logger.info(f"{len(all_trades)}件の取引履歴を保存します。")
            trade_history_df = pd.DataFrame(all_trades, columns=TRADE_HISTORY_COLUMNS)

        trade_history_df.to_csv(
            os.path.join(config.RESULTS_DIR, f"trade_history_{timestamp}.csv"),
            index=False,
            encoding='utf-8-sig'
        )
        logger.info(f"取引履歴ファイルを trade_history_{timestamp}.csv として保存しました。")
    finally:
        logger.info("バックテスト処理完了。")

if __name__ == '__main__':
    main()