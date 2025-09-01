import os
import glob
import logging
import pandas as pd
import backtrader as bt

logger = logging.getLogger(__name__)

def _load_csv_data(filepath, timeframe_str, compression):
    try:
        df = pd.read_csv(filepath, index_col='datetime', parse_dates=True, encoding='utf-8-sig')
        if df.empty:
            logger.warning(f"データファイルが空です: {filepath}")
            return None
        df.columns = [x.lower() for x in df.columns]
        return bt.feeds.PandasData(dataname=df, timeframe=bt.TimeFrame.TFrame(timeframe_str), compression=compression)
    except Exception as e:
        logger.error(f"CSV読み込みまたはデータフィード作成で失敗: {filepath} - {e}")
        return None

def prepare_historical_data_feeds(cerebro, strategy_params, symbol, data_dir, backtest_base_filepath=None):
    """
    [リファクタリング]
    責務を履歴データ(CSV)の読み込みとリサンプリングに限定。
    is_liveフラグは削除。
    """
    logger.info(f"[{symbol}] 履歴データフィードの準備を開始")
    timeframes_config = strategy_params['timeframes']
    short_tf_config = timeframes_config['short']

    if backtest_base_filepath is None:
        short_tf_compression = strategy_params['timeframes']['short']['compression']
        search_pattern = os.path.join(data_dir, f"{symbol}_{short_tf_compression}m_*.csv")
        files = glob.glob(search_pattern)
        if not files: raise FileNotFoundError(f"ベースファイルが見つかりません: {search_pattern}")
        backtest_base_filepath = files[0]
        logger.info(f"ベースファイルを自動検出: {backtest_base_filepath}")

    base_data = _load_csv_data(backtest_base_filepath, short_tf_config['timeframe'], short_tf_config['compression'])
    if base_data is None:
        logger.error(f"[{symbol}] 短期データフィードの作成に失敗しました。")
        return False

    cerebro.adddata(base_data, name=str(symbol))
    logger.info(f"[{symbol}] 短期データフィードを追加しました。")

    for tf_name in ['medium', 'long']:
        tf_config = timeframes_config.get(tf_name)
        if not tf_config: continue
        source_type = tf_config.get('source_type', 'resample')

        if source_type == 'resample':
            cerebro.resampledata(base_data, timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                                 compression=tf_config['compression'], name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データをリサンプリングで追加。")
        elif source_type == 'direct':
            pattern_template = tf_config.get('file_pattern')
            search_pattern = os.path.join(data_dir, pattern_template.format(symbol=symbol))
            data_files = glob.glob(search_pattern)
            if not data_files:
                logger.error(f"[{symbol}] {tf_name}用のデータファイルが見つかりません: {search_pattern}")
                return False
            data_feed = _load_csv_data(data_files[0], tf_config['timeframe'], tf_config['compression'])
            if data_feed is None: return False
            cerebro.adddata(data_feed, name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データを直接読み込み: {data_files[0]}")
    return True