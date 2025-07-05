import os
import glob
import logging
import pandas as pd
import backtrader as bt

# リアルタイム取引用のクラスを動的にインポート
try:
    from src.realtrade.live.yahoo_data import YahooData as LiveData
except ImportError:
    LiveData = None # リアルタイム部品が存在しない場合のエラー回避

logger = logging.getLogger(__name__)

def _load_csv_data(filepath, timeframe_str, compression):
    """単一のCSVファイルを読み込み、PandasDataフィードを返す"""
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

def prepare_data_feeds(cerebro, strategy_params, symbol, data_dir, is_live=False, live_store=None, backtest_base_filepath=None):
    """
    Cerebroに3つの時間足のデータフィード（短期・中期・長期）をセットアップする共通関数。

    :param cerebro: BacktraderのCerebroインスタンス
    :param strategy_params: 'strategy_base.yml'から読み込んだ設定辞書
    :param symbol: 処理対象の銘柄コード
    :param data_dir: バックテスト用のデータが格納されているディレクトリ
    :param is_live: ライブ取引モードかどうか (True/False)
    :param live_store: ライブ取引時に使用するStoreインスタンス
    :param backtest_base_filepath: バックテスト時に基準となる短期足のファイルパス
    """
    logger.info(f"[{symbol}] データフィードの準備を開始 (ライブモード: {is_live})")
    
    timeframes_config = strategy_params['timeframes']
    
    # 1. 短期データフィードの準備
    short_tf_config = timeframes_config['short']
    if is_live:
        if not LiveData:
            raise ImportError("リアルタイム取引部品が見つかりません。'create_realtrade.py'を実行してください。")
        base_data = LiveData(dataname=symbol, store=live_store, 
                             timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']), 
                             compression=short_tf_config['compression'])
    else:
        if not backtest_base_filepath or not os.path.exists(backtest_base_filepath):
            raise FileNotFoundError(f"バックテスト用のベースファイルが見つかりません: {backtest_base_filepath}")
        base_data = _load_csv_data(backtest_base_filepath, short_tf_config['timeframe'], short_tf_config['compression'])

    if base_data is None:
        logger.error(f"[{symbol}] 短期データフィードの作成に失敗しました。処理を中断します。")
        return False
        
    cerebro.adddata(base_data, name=str(symbol))
    logger.info(f"[{symbol}] 短期データフィードを追加しました。")

    # 2. 中期・長期データフィードの準備
    for tf_name in ['medium', 'long']:
        tf_config = timeframes_config.get(tf_name)
        if not tf_config:
            logger.warning(f"[{symbol}] {tf_name}の時間足設定が見つかりません。スキップします。")
            continue

        source_type = tf_config.get('source_type', 'resample')
        
        # ライブ取引時は常にリサンプリング
        if is_live or source_type == 'resample':
            cerebro.resampledata(base_data, 
                                 timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']), 
                                 compression=tf_config['compression'],
                                 name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データフィードをリサンプリングで追加しました。")
        
        elif source_type == 'direct':
            pattern_template = tf_config.get('file_pattern')
            if not pattern_template:
                logger.error(f"[{symbol}] {tf_name}のsource_typeが'direct'ですが、file_patternが未定義です。")
                return False
            
            search_pattern = os.path.join(data_dir, pattern_template.format(symbol=symbol))
            data_files = glob.glob(search_pattern)
            
            if not data_files:
                logger.error(f"[{symbol}] {tf_name}用のデータファイルが見つかりません: {search_pattern}")
                return False
            
            data_feed = _load_csv_data(data_files[0], tf_config['timeframe'], tf_config['compression'])
            if data_feed is None:
                return False
            
            cerebro.adddata(data_feed, name=tf_name)
            logger.info(f"[{symbol}] {tf_name}データフィードを直接読み込みで追加しました: {data_files[0]}")

    return True