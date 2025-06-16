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

def resample_ohlc(df, rule):
    #価格データを指定の時間足にリサンプリングする
    ohlc_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    return df.resample(rule).agg(ohlc_dict).dropna()

def plot_multi_timeframe_charts():
    logger.info("--- マルチタイムフレーム・チャート生成開始 ---")

    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    trades_df = pd.DataFrame() 
    if trade_history_path:
        logger.info(f"取引履歴ファイルを読み込みます: {trade_history_path}")
        trades_df = pd.read_csv(trade_history_path, parse_dates=['エントリー日時', '決済日時'])
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

    p_ind = strategy_params['indicators']
    p_filter = strategy_params['filters']
    p_tf = strategy_params['timeframes']

    for symbol in all_symbols:
        try:
            logger.info(f"銘柄 {symbol} のチャートを生成中...")
            
            # --- データの準備 ---
            csv_pattern = os.path.join(config.DATA_DIR, f"{symbol}*.csv")
            data_files = glob.glob(csv_pattern)
            if not data_files:
                logger.warning(f"{symbol} の価格データが見つかりません。スキップします。")
                continue
            
            base_df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
            base_df.columns = [x.lower() for x in base_df.columns]
            
            if base_df.index.tz is not None:
                base_df.index = base_df.index.tz_localize(None)

            symbol_trades = trades_df[trades_df['銘柄'] == int(symbol)].copy() if not trades_df.empty else pd.DataFrame()

            # --- 短期チャートの描画 (5分足) ---
            df_short = base_df.copy()
            df_short['ema_fast'] = df_short['close'].ewm(span=p_ind['short_ema_fast'], adjust=False).mean()
            df_short['ema_slow'] = df_short['close'].ewm(span=p_ind['short_ema_slow'], adjust=False).mean()
            
            buy_markers = pd.Series(np.nan, index=df_short.index)
            sell_markers = pd.Series(np.nan, index=df_short.index)
            sl_lines = pd.Series(np.nan, index=df_short.index)
            tp_lines = pd.Series(np.nan, index=df_short.index)

            if not symbol_trades.empty:
                for _, trade in symbol_trades.iterrows():
                    entry_idx = df_short.index.get_indexer([trade['エントリー日時']], method='nearest')[0]
                    exit_idx = df_short.index.get_indexer([trade['決済日時']], method='nearest')[0]
                    entry_ts = df_short.index[entry_idx]
                    exit_ts = df_short.index[exit_idx]
                    
                    if trade['方向'] == 'BUY':
                        buy_markers.loc[entry_ts] = df_short['low'].iloc[entry_idx] * 0.99
                    else: # SELL
                        sell_markers.loc[entry_ts] = df_short['high'].iloc[entry_idx] * 1.01
                    sl_lines.loc[entry_ts:exit_ts] = trade['ストップロス価格']
                    tp_lines.loc[entry_ts:exit_ts] = trade['テイクプロフィット価格']
            
            short_plots = [
                mpf.make_addplot(df_short[['ema_fast', 'ema_slow']]),
                mpf.make_addplot(buy_markers, type='scatter', marker='^', color='g', markersize=100),
                mpf.make_addplot(sell_markers, type='scatter', marker='v', color='r', markersize=100),
                mpf.make_addplot(sl_lines, color='red', linestyle=':'),
                mpf.make_addplot(tp_lines, color='green', linestyle=':'),
            ]
            
            save_path_short = os.path.join(config.CHART_DIR, f'chart_short_{symbol}.png')
            mpf.plot(df_short, type='candle', style='yahoo', title=f"{symbol} Short-Term ({p_tf['short']['compression']}min)",
                     volume=True, addplot=short_plots, figsize=(20, 10),
                     savefig=dict(fname=save_path_short, dpi=100), tight_layout=True)
            logger.info(f"短期チャートを保存しました: {save_path_short}")


            # --- 中期チャートの描画 (60分足) ---
            df_medium = resample_ohlc(base_df, f"{p_tf['medium']['compression']}min")
            delta = df_medium['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=p_ind['medium_rsi_period']).mean()
            rs = gain / loss
            df_medium['rsi'] = 100 - (100 / (1 + rs))
            
            medium_plots = [
                mpf.make_addplot(df_medium['rsi'], panel=2, color='b', ylabel='RSI'),
                mpf.make_addplot(pd.Series(p_filter['medium_rsi_upper'], index=df_medium.index), panel=2, color='r', linestyle='--'),
                mpf.make_addplot(pd.Series(p_filter['medium_rsi_lower'], index=df_medium.index), panel=2, color='g', linestyle='--')
            ]

            save_path_medium = os.path.join(config.CHART_DIR, f'chart_medium_{symbol}.png')
            mpf.plot(df_medium, type='candle', style='yahoo', title=f"{symbol} Medium-Term ({p_tf['medium']['compression']}min)",
                     volume=True, addplot=medium_plots, figsize=(20, 10), panel_ratios=(3,1,2),
                     savefig=dict(fname=save_path_medium, dpi=100), tight_layout=True)
            logger.info(f"中期チャートを保存しました: {save_path_medium}")


            # --- 長期チャートの描画 (日足) ---
            df_long = resample_ohlc(base_df, 'D')
            df_long['ema_long'] = df_long['close'].ewm(span=p_ind['long_ema_period'], adjust=False).mean()
            
            long_plots = [ mpf.make_addplot(df_long['ema_long'], color='purple') ]

            save_path_long = os.path.join(config.CHART_DIR, f'chart_long_{symbol}.png')
            mpf.plot(df_long, type='candle', style='yahoo', title=f'{symbol} Long-Term (Daily)',
                     volume=True, addplot=long_plots, figsize=(20, 10),
                     savefig=dict(fname=save_path_long, dpi=100), tight_layout=True)
            logger.info(f"長期チャートを保存しました: {save_path_long}")

        except Exception as e:
            logger.error(f"銘柄 {symbol} のチャート生成中にエラーが発生しました。", exc_info=True)

    logger.info("--- 全てのチャート生成が完了しました ---")

def main():
    logger_setup.setup_logging()
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    
    plot_multi_timeframe_charts()

if __name__ == '__main__':
    main()