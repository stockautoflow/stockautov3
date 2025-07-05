import os

# ==============================================================================
# ファイル: create_backtest.py
# 実行方法: python create_backtest.py
# Ver. 00-01
# 変更点:
#   - run_backtest.py:
#     - データフィード準備のロジックを全面的に削除。
#     - 新しい共通部品 `src.core.data_preparer.prepare_data_feeds` を
#       呼び出すように変更し、コードを大幅に簡素化。
# ==============================================================================

backtest_files = {
    "src/backtest/__init__.py": "",
    "src/backtest/config_backtest.py": """
import os
import logging
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'results', 'backtest')
LOG_DIR = os.path.join(BASE_DIR, 'log')
INITIAL_CAPITAL = 5000000
COMMISSION_PERC = 0.001
SLIPPAGE_PERC = 0.0002
LOG_LEVEL = logging.INFO
""",
    "src/backtest/report.py": """
import pandas as pd
from datetime import datetime
from . import config_backtest as config

def _format_condition_for_report(cond):
    tf = cond['timeframe'][0].upper()
    cond_type = cond.get('type')
    if cond_type in ['crossover', 'crossunder']:
        i1, i2 = cond['indicator1'], cond['indicator2']
        p1 = ",".join(map(str, i1.get('params', {}).values()))
        p2 = ",".join(map(str, i2.get('params', {}).values()))
        op = " crosses over " if cond_type == 'crossover' else " crosses under "
        return f"{tf}: {i1['name']}({p1}){op}{i2['name']}({p2})"
    ind_def = cond['indicator']
    ind_str = f"{ind_def['name']}({','.join(map(str, ind_def.get('params', {}).values()))})"
    comp_str = 'is between' if cond['compare'] == 'between' else cond['compare']
    tgt = cond['target']
    tgt_type, tgt_str = tgt.get('type'), ""
    if tgt_type == 'data':
        tgt_str = tgt.get('value', '')
    elif tgt_type == 'indicator':
        tgt_ind_def = tgt.get('indicator', {})
        tgt_params_str = ",".join(map(str, tgt_ind_def.get('params', {}).values()))
        tgt_str = f"{tgt_ind_def.get('name', '')}({tgt_params_str})"
    elif tgt_type == 'values':
        value = tgt.get('value')
        tgt_str = f"{value[0]} and {value[1]}" if isinstance(value, list) and len(value) > 1 else str(value)
    return f"{tf}: {ind_str} {comp_str} {tgt_str}"

def _format_exit_for_report(exit_cond):
    p = exit_cond.get('params', {})
    tf = exit_cond.get('timeframe','?')[0]
    mult, period = p.get('multiplier'), p.get('period')
    if exit_cond.get('type') == 'atr_multiple':
        return f"Fixed ATR(t:{tf}, p:{period}) * {mult}"
    if exit_cond.get('type') == 'atr_stoptrail':
        return f"Native StopTrail ATR(t:{tf}, p:{period}) * {mult}"
    return "Unknown"

def generate_report(all_results, strategy_params, start_date, end_date):
    total_net = sum(r['pnl_net'] for r in all_results)
    total_won = sum(r['gross_won'] for r in all_results)
    total_lost = sum(r['gross_lost'] for r in all_results)
    total_trades = sum(r['total_trades'] for r in all_results)
    total_win = sum(r['win_trades'] for r in all_results)
    win_rate = (total_win / total_trades) * 100 if total_trades > 0 else 0
    pf = abs(total_won / total_lost) if total_lost != 0 else float('inf')
    avg_profit = total_won / total_win if total_win > 0 else 0
    avg_loss = total_lost / (total_trades - total_win) if (total_trades - total_win) > 0 else 0
    rr = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')
    p = strategy_params
    long_c = "Long: " + " AND ".join([_format_condition_for_report(c) for c in p.get('entry_conditions',{}).get('long',[])]) if p.get('trading_mode',{}).get('long_enabled') else ""
    short_c = "Short: " + " AND ".join([_format_condition_for_report(c) for c in p.get('entry_conditions',{}).get('short',[])]) if p.get('trading_mode',{}).get('short_enabled') else ""
    tp_desc = _format_exit_for_report(p.get('exit_conditions',{}).get('take_profit',{})) if p.get('exit_conditions',{}).get('take_profit') else "N/A"
    return pd.DataFrame({
        '項目': ["分析日時", "分析期間", "初期資金", "トレード毎リスク", "手数料", "スリッページ", "戦略名", "エントリーロジック", "損切りロジック", "利確ロジック", "---", "純利益", "総利益", "総損失", "PF", "勝率", "総トレード数", "勝トレード", "負トレード", "平均利益", "平均損失", "RR比"],
        '結果': [datetime.now().strftime('%Y-%m-%d %H:%M'), f"{start_date.strftime('%y/%m/%d')}-{end_date.strftime('%y/%m/%d')}", f"¥{config.INITIAL_CAPITAL:,.0f}", f"{p.get('sizing',{}).get('risk_per_trade',0):.1%}", f"{config.COMMISSION_PERC:.3%}", f"{config.SLIPPAGE_PERC:.3%}", p.get('strategy_name','N/A'), " | ".join(filter(None, [long_c, short_c])), _format_exit_for_report(p.get('exit_conditions',{}).get('stop_loss',{})), tp_desc, "---", f"¥{total_net:,.0f}", f"¥{total_won:,.0f}", f"¥{total_lost:,.0f}", f"{pf:.2f}", f"{win_rate:.2f}%", total_trades, total_win, total_trades-total_win, f"¥{avg_profit:,.0f}", f"¥{avg_loss:,.0f}", f"{rr:.2f}"],
    })
""",
    "src/backtest/run_backtest.py": """
import backtrader as bt
import pandas as pd
import os
import glob
import yaml
import logging
from datetime import datetime

from src.core.util import logger as logger_setup
from src.core.util import notifier
from src.core import strategy as btrader_strategy
from src.core.data_preparer import prepare_data_feeds # 【修正】共通部品をインポート
from . import config_backtest as config
from . import report as report_generator

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
        exit_price = (trade.value + pnl) / size if size > 0 else trade.price
        self.trades.append({
            '銘柄': self.symbol, '方向': 'BUY' if trade.long else 'SELL', '数量': size,
            'エントリー価格': trade.price, 'エントリー日時': bt.num2date(trade.dtopen).replace(tzinfo=None).isoformat(),
            'エントリー根拠': getattr(trade, 'entry_reason_for_trade', 'N/A'),
            '決済価格': exit_price, '決済日時': bt.num2date(trade.dtclose).replace(tzinfo=None).isoformat(),
            '決済根拠': "Take Profit" if trade.pnlcomm >= 0 else "Stop Loss",
            '損益': trade.pnl, '損益(手数料込)': trade.pnlcomm,
            'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price
        })
    def stop(self):
        if not self.strategy.position: return
        pos = self.strategy.position
        entry_price, size = pos.price, pos.size
        exit_price = self.strategy.data.close[0]
        pnl = (exit_price - entry_price) * size
        commission = (abs(size) * entry_price * config.COMMISSION_PERC) + (abs(size) * exit_price * config.COMMISSION_PERC)
        self.trades.append({
            '銘柄': self.symbol, '方向': 'BUY' if size > 0 else 'SELL', '数量': abs(size),
            'エントリー価格': entry_price, 'エントリー日時': self.strategy.current_position_entry_dt.isoformat(),
            'エントリー根拠': self.strategy.entry_reason,
            '決済価格': exit_price, '決済日時': self.strategy.data.datetime.datetime(0).isoformat(),
            '決済根拠': "End of Backtest", '損益': pnl, '損益(手数料込)': pnl - commission,
            'ストップロス価格': self.strategy.risk_per_share, 'テイクプロフィット価格': self.strategy.tp_price
        })
    def get_analysis(self):
        return self.trades

def run_backtest_for_symbol(symbol, base_filepath, strategy_cls, strategy_params):
    logger.info(f"▼▼▼ バックテスト実行中: {symbol} ▼▼▼")
    try:
        df_for_dates = pd.read_csv(base_filepath, index_col='datetime', parse_dates=True)
        if df_for_dates.empty:
            logger.warning(f"データファイルが空のためスキップ: {base_filepath}")
            return None, None, None, None
        start_date, end_date = df_for_dates.index[0], df_for_dates.index[-1]
    except Exception as e:
        logger.error(f"期間取得のためCSV読み込み中にエラー: {base_filepath} - {e}")
        return None, None, None, None

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.addstrategy(strategy_cls, strategy_params=strategy_params)
    
    # 【修正】データフィードの準備を共通部品に委譲
    success = prepare_data_feeds(cerebro, strategy_params, symbol, config.DATA_DIR, 
                                 is_live=False, backtest_base_filepath=base_filepath)
    if not success:
        logger.error(f"[{symbol}] のデータフィード準備に失敗しました。")
        return None, None, None, None

    cerebro.broker.set_cash(config.INITIAL_CAPITAL)
    cerebro.broker.setcommission(commission=config.COMMISSION_PERC)
    cerebro.broker.set_slippage_perc(perc=config.SLIPPAGE_PERC)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    cerebro.addanalyzer(TradeList, _name='tradelist')

    try:
        results = cerebro.run()
        strat = results[0]
        trade_analysis = strat.analyzers.trade.get_analysis()
        trade_list = strat.analyzers.tradelist.get_analysis()
        return {
            'symbol': symbol,
            'pnl_net': trade_analysis.get('pnl', {}).get('net', {}).get('total', 0),
            'gross_won': trade_analysis.get('won', {}).get('pnl', {}).get('total', 0),
            'gross_lost': trade_analysis.get('lost', {}).get('pnl', {}).get('total', 0),
            'total_trades': trade_analysis.get('total', {}).get('total', 0),
            'win_trades': trade_analysis.get('won', {}).get('total', 0)
        }, start_date, end_date, trade_list
    except (ZeroDivisionError, IndexError) as e:
        logger.warning(f"銘柄 {symbol} のバックテスト中にエラーが発生しました ({type(e).__name__})。スキップします。")
        return None, None, None, None

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='backtest')
    logger.info("--- 単一戦略バックテスト開始 ---")
    
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR]:
        if not os.path.exists(dir_path): os.makedirs(dir_path)
        
    strategy_file_path = os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml')
    with open(strategy_file_path, 'r', encoding='utf-8') as f:
        strategy_params = yaml.safe_load(f)

    short_tf_compression = strategy_params['timeframes']['short']['compression']
    base_file_pattern = f"*_{short_tf_compression}m_*.csv"
    base_csv_files = glob.glob(os.path.join(config.DATA_DIR, base_file_pattern))
    
    if not base_csv_files:
        logger.error(f"{config.DATA_DIR}にベースデータが見つかりません (パターン: {base_file_pattern})。"); return

    all_results, all_trades, all_details, start_dates, end_dates = [], [], [], [], []
    for filepath in sorted(base_csv_files):
        symbol = os.path.basename(filepath).split('_')[0]
        stats, start_date, end_date, trade_list = run_backtest_for_symbol(
            symbol, filepath, btrader_strategy.DynamicStrategy, strategy_params
        )
        if stats:
            all_results.append(stats)
            all_trades.extend(trade_list)
            if start_date: start_dates.append(start_date)
            if end_date: end_dates.append(end_date)
            win_trades, total_trades = stats['win_trades'], stats['total_trades']
            lost_trades = total_trades - win_trades
            win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
            pf = abs(stats['gross_won'] / stats['gross_lost']) if stats['gross_lost'] != 0 else float('inf')
            avg_win = stats['gross_won'] / win_trades if win_trades > 0 else 0
            avg_loss = stats['gross_lost'] / lost_trades if lost_trades > 0 else 0
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            all_details.append({
                "銘柄": stats['symbol'], "純利益": f"¥{stats['pnl_net']:,.2f}",
                "総利益": f"¥{stats['gross_won']:,.2f}", "総損失": f"¥{stats['gross_lost']:,.2f}",
                "PF": f"{pf:.2f}", "勝率": f"{win_rate:.2f}%", "総トレード数": total_trades,
                "勝トレード": win_trades, "負トレード": lost_trades, "平均利益": f"¥{avg_win:,.2f}",
                "平均損失": f"¥{avg_loss:,.2f}", "RR比": f"{rr:.2f}"
            })

    if not all_results or not start_dates or not end_dates:
        logger.warning("有効な結果/期間がなくレポート生成をスキップします。"); return

    report_df = report_generator.generate_report(all_results, strategy_params, min(start_dates), max(end_dates))
    timestamp = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    
    report_df.to_csv(os.path.join(config.RESULTS_DIR, f"summary_{timestamp}.csv"), index=False, encoding='utf-8-sig')
    if all_details: pd.DataFrame(all_details).to_csv(os.path.join(config.RESULTS_DIR, f"detail_{timestamp}.csv"), index=False, encoding='utf-8-sig')
    if all_trades: pd.DataFrame(all_trades).to_csv(os.path.join(config.RESULTS_DIR, f"trade_history_{timestamp}.csv"), index=False, encoding='utf-8-sig')

    logger.info("\\n\\n★★★ 全銘柄バックテストサマリー ★★★\\n" + report_df.to_string())
    notifier.send_email(subject="【Backtrader】単一戦略バックテスト完了", body=f"バックテストが完了しました。\\n\\n--- サマリー ---\\n{report_df.to_string()}")

if __name__ == '__main__':
    main()
"""
}

def create_files(files_dict):
    for filename, content in files_dict.items():
        if os.path.dirname(filename) and not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"  - ファイル作成: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- 4. backtestパッケージの生成を開始します ---")
    create_files(backtest_files)
    print("backtestパッケージの生成が完了しました。")
