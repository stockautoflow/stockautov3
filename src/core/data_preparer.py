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
        # [修正] バックテスト/シミュレーションモードの場合
        # ファイルパスが指定されていない場合、銘柄コードから自動で検索する
        if backtest_base_filepath is None:
            logger.warning(f"バックテスト用のベースファイルパスが指定されていません。銘柄コード {symbol} から自動検索を試みます。")
            short_tf_compression = strategy_params['timeframes']['short']['compression']
            search_pattern = os.path.join(data_dir, f"{symbol}_{short_tf_compression}m_*.csv")
            files = glob.glob(search_pattern)
            if not files:
                raise FileNotFoundError(f"バックテスト/シミュレーション用のベースファイルが見つかりません。検索パターン: {search_pattern}")
            backtest_base_filepath = files[0] # 最初に見つかったファイルを使用
            logger.info(f"ベースファイルを自動検出しました: {backtest_base_filepath}")

        if not os.path.exists(backtest_base_filepath):
            raise FileNotFoundError(f"指定されたバックテスト用のベースファイルが見つかりません: {backtest_base_filepath}")
        
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