import os
import glob
import pandas as pd
import numpy as np
import mplfinance as mpf
import config_backtrader as config
import logger_setup
import logging
import yaml
import matplotlib
import matplotlib.lines as mlines
import matplotlib.pyplot as plt

matplotlib.use('Agg')
logger = logging.getLogger(__name__)

def find_latest_report(report_dir, prefix):
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    return max(files, key=os.path.getctime) if files else None

def get_all_symbols(data_dir):
    file_pattern = os.path.join(data_dir, f"*_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
    files = glob.glob(file_pattern)
    symbols = [os.path.basename(f).split('_')[0] for f in files]
    return sorted(list(set(symbols)))

def calculate_indicators(price_df, strategy_params):
    p = strategy_params['indicators']
    price_df['ema_fast'] = price_df['close'].ewm(span=p['short_ema_fast'], adjust=False).mean()
    price_df['ema_slow'] = price_df['close'].ewm(span=p['short_ema_slow'], adjust=False).mean()
    rsi_period_adjusted = p['medium_rsi_period'] * 12
    delta = price_df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period_adjusted).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period_adjusted).mean()
    rs = gain / loss
    price_df['rsi'] = 100 - (100 / (1 + rs))
    ema_long_period_adjusted = p['long_ema_period'] * 78 
    price_df['ema_long'] = price_df['close'].ewm(span=ema_long_period_adjusted, adjust=False).mean()
    return price_df

def plot_enhanced_charts():
    logger.info("--- 高機能チャート生成開始 ---")

    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    trades_df = pd.DataFrame() 
    if trade_history_path:
        logger.info(f"取引履歴ファイルを読み込みます: {trade_history_path}")
        trades_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
        if trades_df['エントリー日時'].dt.tz is not None:
            trades_df['エントリー日時'] = trades_df['エントリー日時'].dt.tz_localize(None)
        if trades_df['決済日時'].dt.tz is not None:
            trades_df['決済日時'] = trades_df['決済日時'].dt.tz_localize(None)
    else:
        logger.warning("取引履歴レポートが見つかりません。")

    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("strategy.yml が見つかりません。")
        return

    all_symbols = get_all_symbols(config.DATA_DIR)
    if not all_symbols:
        logger.error(f"{config.DATA_DIR}に価格データが見つかりません。")
        return

    for symbol in all_symbols:
        try:
            logger.info(f"銘柄 {symbol} のチャートを生成中...")
            
            symbol_trades = trades_df[trades_df['銘柄'] == int(symbol)].copy() if not trades_df.empty else pd.DataFrame()
            
            csv_pattern = os.path.join(config.DATA_DIR, f"{symbol}*.csv")
            data_files = glob.glob(csv_pattern)
            if not data_files:
                logger.warning(f"{symbol} の価格データが見つかりません。スキップします。")
                continue
            
            price_df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
            price_df.columns = [x.lower() for x in price_df.columns]
            
            if price_df.index.tz is not None:
                price_df.index = price_df.index.tz_localize(None)

            price_df = calculate_indicators(price_df, strategy_params)

            buy_markers = pd.Series(np.nan, index=price_df.index)
            sell_markers = pd.Series(np.nan, index=price_df.index)
            sl_lines = pd.Series(np.nan, index=price_df.index)
            tp_lines = pd.Series(np.nan, index=price_df.index)
            rsi_dots = pd.Series(np.nan, index=price_df.index)

            if not symbol_trades.empty:
                for _, trade in symbol_trades.iterrows():
                    try:
                        entry_idx = price_df.index.get_indexer([trade['エントリー日時']], method='nearest')[0]
                        exit_idx = price_df.index.get_indexer([trade['決済日時']], method='nearest')[0]
                        
                        entry_timestamp = price_df.index[entry_idx]
                        exit_timestamp = price_df.index[exit_idx]
                        
                        if trade['方向'] == 'BUY':
                            buy_markers.loc[entry_timestamp] = price_df['low'].iloc[entry_idx] * 0.99
                        else: # SELL
                            sell_markers.loc[entry_timestamp] = price_df['high'].iloc[entry_idx] * 1.01

                        sl_lines.loc[entry_timestamp:exit_timestamp] = trade['ストップロス価格']
                        tp_lines.loc[entry_timestamp:exit_timestamp] = trade['テイクプロフィット価格']
                        
                        rsi_dots.loc[entry_timestamp] = trade['エントリー時中期RSI']

                    except Exception as e:
                        logger.warning(f"タイムスタンプ {trade['エントリー日時']} の処理中にエラーが発生しました: {e}。このトレードはスキップされます。")
                        continue

            main_plots = [
                mpf.make_addplot(price_df['ema_fast'], color='blue', width=0.7, panel=0),
                mpf.make_addplot(price_df['ema_slow'], color='orange', width=0.7, panel=0),
                mpf.make_addplot(price_df['ema_long'], color='purple', width=1.0, linestyle='--', panel=0),
                mpf.make_addplot(buy_markers, type='scatter', marker='^', color='g', markersize=100, panel=0),
                mpf.make_addplot(sell_markers, type='scatter', marker='v', color='r', markersize=100, panel=0),
                mpf.make_addplot(sl_lines, color='red', width=1.0, linestyle=':', panel=0),
                mpf.make_addplot(tp_lines, color='green', width=1.0, linestyle=':', panel=0),
            ]
            
            rsi_plots = [
                mpf.make_addplot(price_df['rsi'], color='cyan', width=0.8, panel=2, ylabel='RSI'),
                mpf.make_addplot(rsi_dots, type='scatter', marker='o', color='magenta', markersize=50, panel=2),
                mpf.make_addplot(pd.Series(strategy_params['filters']['medium_rsi_upper'], index=price_df.index), 
                                 color='gray', linestyle='--', panel=2),
                mpf.make_addplot(pd.Series(strategy_params['filters']['medium_rsi_lower'], index=price_df.index), 
                                 color='gray', linestyle='--', panel=2),
            ]

            all_plots = main_plots + rsi_plots
            
            fig, axes = mpf.plot(price_df, type='candle', style='yahoo',
                                 title=f'{symbol} Enhanced Trade Analysis',
                                 volume=True, volume_panel=1, panel_ratios=(4, 1, 2),
                                 addplot=all_plots,
                                 figsize=(20, 12),
                                 tight_layout=True,
                                 returnfig=True)

            p_ind = strategy_params['indicators']
            legend_handles = [
                mlines.Line2D([], [], color='blue', lw=0.7, label=f"EMA Fast ({p_ind['short_ema_fast']})"),
                mlines.Line2D([], [], color='orange', lw=0.7, label=f"EMA Slow ({p_ind['short_ema_slow']})"),
                mlines.Line2D([], [], color='purple', lw=1.0, linestyle='--', label=f"EMA Long ({p_ind['long_ema_period']})"),
                mlines.Line2D([], [], color='g', marker='^', linestyle='None', markersize=10, label='Buy Entry'),
                mlines.Line2D([], [], color='r', marker='v', linestyle='None', markersize=10, label='Sell Entry'),
                mlines.Line2D([], [], color='red', lw=1.0, linestyle=':', label='Stop Loss'),
                mlines.Line2D([], [], color='green', lw=1.0, linestyle=':', label='Take Profit'),
            ]
            axes[0].legend(handles=legend_handles, loc='upper left')

            save_path = os.path.join(config.CHART_DIR, f'chart_enhanced_{symbol}.png')
            fig.savefig(save_path, dpi=100)
            plt.close(fig)
            
            logger.info(f"高機能チャートを保存しました: {save_path}")

        except Exception as e:
            logger.error(f"銘柄 {symbol} のチャート生成中にエラーが発生しました。", exc_info=True)

    logger.info("--- 全ての高機能チャート生成が完了しました ---")

def main():
    logger_setup.setup_logging()
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    plot_enhanced_charts()

if __name__ == '__main__':
    main()