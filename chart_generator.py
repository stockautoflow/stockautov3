import os
import glob
import pandas as pd
import mplfinance as mpf
import config_backtrader as config
import logger_setup
import logging
import yaml
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

def find_latest_report(report_dir, prefix):
    #指定されたプレフィックスを持つ最新のレポートファイルを見つける
    search_pattern = os.path.join(report_dir, f"{prefix}_*.csv")
    files = glob.glob(search_pattern)
    if not files:
        return None
    return max(files, key=os.path.getctime)

def plot_charts_for_all():
    logger.info("--- チャート生成開始 ---")

    trade_history_path = find_latest_report(config.REPORT_DIR, "trade_history")
    if not trade_history_path:
        logger.error(f"{config.REPORT_DIR} に取引履歴レポートが見つかりません。")
        logger.info("先に 'python run_backtrader.py' を実行してください。")
        return

    logger.info(f"取引履歴ファイルを読み込みます: {trade_history_path}")
    # ★★★ 修正点 ★★★
    # タイムゾーン情報を削除して読み込む
    trades_df = pd.read_csv(trade_history_path)
    trades_df['エントリー日時'] = pd.to_datetime(trades_df['エントリー日時']).dt.tz_localize(None)
    trades_df['決済日時'] = pd.to_datetime(trades_df['決済日時']).dt.tz_localize(None)

    try:
        with open('strategy.yml', 'r', encoding='utf-8') as f:
            strategy_params = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("strategy.yml が見つかりません。")
        return

    symbols = trades_df['銘柄'].unique()
    for symbol in symbols:
        try:
            logger.info(f"銘柄 {symbol} のチャートを生成中...")
            
            symbol_trades = trades_df[trades_df['銘柄'] == symbol]

            csv_pattern = os.path.join(config.DATA_DIR, f"{symbol}_{config.BACKTEST_CSV_BASE_COMPRESSION}m_*.csv")
            data_files = glob.glob(csv_pattern)
            if not data_files:
                logger.warning(f"銘柄 {symbol} の価格データファイルが見つかりません。スキップします。")
                continue
            
            price_df = pd.read_csv(data_files[0], index_col='datetime', parse_dates=True)
            price_df.columns = [x.lower() for x in price_df.columns]
            
            p = strategy_params['indicators']
            price_df['ema_fast'] = price_df['close'].ewm(span=p['short_ema_fast'], adjust=False).mean()
            price_df['ema_slow'] = price_df['close'].ewm(span=p['short_ema_slow'], adjust=False).mean()
            
            buy_markers = pd.Series(float('nan'), index=price_df.index)
            sell_markers = pd.Series(float('nan'), index=price_df.index)
            
            for _, trade in symbol_trades.iterrows():
                # ★★★ 修正点: get_locからget_indexerに変更 ★★★
                entry_idx = price_df.index.get_indexer([trade['エントリー日時']], method='nearest')[0]
                exit_idx = price_df.index.get_indexer([trade['決済日時']], method='nearest')[0]
                buy_markers.iloc[entry_idx] = price_df['low'].iloc[entry_idx] * 0.99
                sell_markers.iloc[exit_idx] = price_df['high'].iloc[exit_idx] * 1.01

            start_date = symbol_trades['エントリー日時'].min() - pd.Timedelta(days=1)
            end_date = symbol_trades['決済日時'].max() + pd.Timedelta(days=1)
            plot_df = price_df.loc[start_date:end_date]
            
            addplots = [
                mpf.make_addplot(plot_df['ema_fast'], color='blue', width=0.7),
                mpf.make_addplot(plot_df['ema_slow'], color='orange', width=0.7),
                mpf.make_addplot(buy_markers.loc[start_date:end_date], type='scatter', marker='^', color='g', markersize=100),
                mpf.make_addplot(sell_markers.loc[start_date:end_date], type='scatter', marker='v', color='r', markersize=100)
            ]
            
            save_path = os.path.join(config.CHART_DIR, f'chart_{symbol}.png')
            mpf.plot(plot_df, type='candle', style='yahoo',
                     title=f'{symbol} Trade Chart',
                     volume=True,
                     addplot=addplots,
                     figsize=(16,9),
                     savefig=save_path, 
                     tight_layout=True)
            
            logger.info(f"チャートを保存しました: {save_path}")

        except Exception as e:
            logger.error(f"銘柄 {symbol} のチャート生成中にエラーが発生しました: {e}")

    logger.info("--- 全てのチャート生成が完了しました ---")

def main():
    logger_setup.setup_logging()
    for dir_path in [config.DATA_DIR, config.RESULTS_DIR, config.LOG_DIR, config.REPORT_DIR, config.CHART_DIR]:
        if not os.path.exists(dir_path): os.makedirs(dir_path)
    
    plot_charts_for_all()

if __name__ == '__main__':
    main()