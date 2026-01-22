import backtrader as bt
import copy
import yaml
import logging
import os
import glob
import pandas as pd
from datetime import datetime

from .strategy import RealTradeStrategy
from .rakuten.rakuten_broker import RakutenBroker
from .rakuten.rakuten_data import RakutenData

logger = logging.getLogger(__name__)

class CerebroFactory:
    def __init__(self, strategy_catalog, base_strategy_params, data_dir, statistics_map):
        self.strategy_catalog = strategy_catalog
        self.base_strategy_params = base_strategy_params
        self.data_dir = data_dir
        self.statistics_map = statistics_map
        logger.info("CerebroFactory initialized.")

    def create_instance(self, symbol: str, strategy_name: str, connector):
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not entry_strategy_def:
            logger.warning(f"Strategy definition not found for '{strategy_name}'. Skipping symbol {symbol}.")
            return None

        strategy_params = copy.deepcopy(self.base_strategy_params)
        strategy_params.update(entry_strategy_def)
        strategy_params['strategy_name'] = strategy_name

        try:
            cerebro = bt.Cerebro(runonce=False)
            cerebro.setbroker(RakutenBroker(bridge=connector))
            
            # 短期足設定
            short_tf_config = strategy_params['timeframes']['short']
            compression = short_tf_config['compression']
            
            # [変更] CSVファイルパスの特定
            search_pattern = os.path.join(self.data_dir, f"{symbol}_{compression}m_*.csv")
            files = glob.glob(search_pattern)
            
            hist_df = pd.DataFrame()
            save_file_path = None

            if files:
                latest_file = max(files, key=os.path.getctime)
                save_file_path = latest_file
                try:
                    df = pd.read_csv(latest_file, index_col='datetime', parse_dates=True)
                    if not df.empty:
                        # タイムゾーン情報を除去してBacktraderに渡す(BT内部で処理するため)
                        if df.index.tz is not None: df.index = df.index.tz_localize(None)
                        df.columns = [x.lower() for x in df.columns]
                        hist_df = df
                        logger.info(f"[{symbol}] Loaded {len(hist_df)} bars from {latest_file}")
                except Exception as e:
                    logger.warning(f"[{symbol}] Could not load historical data from {latest_file}: {e}")
            
            # ファイルが存在しない場合は新規作成パスを設定 (年単位)
            if not save_file_path:
                year = datetime.now().year
                save_file_path = os.path.join(self.data_dir, f"{symbol}_{compression}m_{year}.csv")
                logger.info(f"[{symbol}] 新規保存先を設定: {save_file_path}")

            # [変更] RakutenDataにsave_fileを渡す
            primary_data = RakutenData(
                dataname=hist_df,
                bridge=connector,
                symbol=symbol,
                timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
                compression=short_tf_config['compression'],
                save_file=save_file_path
            )
            cerebro.adddata(primary_data, name=str(symbol))

            # リサンプリング
            for tf_name in ['medium', 'long']:
                if tf_config := strategy_params['timeframes'].get(tf_name):
                    cerebro.resampledata(
                        primary_data,
                        timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                        compression=tf_config['compression'],
                        name=tf_name
                    )
            
            # 戦略追加
            stats_key = (strategy_name, str(symbol))
            symbol_statistics = self.statistics_map.get(stats_key, {})
            strategy_components = { 'statistics': symbol_statistics }
            
            cerebro.addstrategy(
                RealTradeStrategy, 
                strategy_params=strategy_params, 
                strategy_components=strategy_components
            )
            
            return cerebro

        except Exception as e:
            logger.error(f"[{symbol}] Failed to create Cerebro instance: {e}", exc_info=True)
            return None