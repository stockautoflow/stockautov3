import backtrader as bt
import copy
import yaml
import logging
import os
import glob
import pandas as pd

# 必要なクラスをインポート
from .strategy import RealTradeStrategy
from .rakuten.rakuten_broker import RakutenBroker
from .rakuten.rakuten_data import RakutenData

logger = logging.getLogger(__name__)

class CerebroFactory:
    """
    Cerebroインスタンスの生成とセットアップに関する複雑な処理をカプセル化する。
    """
    def __init__(self, strategy_catalog, base_strategy_params, data_dir):
        self.strategy_catalog = strategy_catalog
        self.base_strategy_params = base_strategy_params
        self.data_dir = data_dir
        logger.info("CerebroFactory initialized.")

    def create_instance(self, symbol: str, strategy_name: str, connector):
        """
        指定された銘柄と戦略に基づき、実行可能なCerebroインスタンスを生成する。
        """
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not entry_strategy_def:
            logger.warning(f"Strategy definition not found for '{strategy_name}'. Skipping symbol {symbol}.")
            return None

        # 銘柄ごとの最終的な戦略パラメータを構築
        strategy_params = copy.deepcopy(self.base_strategy_params)
        strategy_params.update(entry_strategy_def)
        strategy_params['strategy_name'] = strategy_name

        try:
            cerebro = bt.Cerebro(runonce=False)
            
            # 1. ブローカーを設定
            cerebro.setbroker(RakutenBroker(bridge=connector))
            
            # 2. ライブデータフィードと履歴データを設定
            short_tf_config = strategy_params['timeframes']['short']
            compression = short_tf_config['compression']
            search_pattern = os.path.join(self.data_dir, f"{symbol}_{compression}m_*.csv")
            files = glob.glob(search_pattern)
            
            hist_df = pd.DataFrame()
            if files:
                latest_file = max(files, key=os.path.getctime)
                try:
                    df = pd.read_csv(latest_file, index_col='datetime', parse_dates=True)
                    if not df.empty:
                        if df.index.tz is not None: df.index = df.index.tz_localize(None)
                        df.columns = [x.lower() for x in df.columns]
                        hist_df = df
                        logger.info(f"[{symbol}] Loaded {len(hist_df)} bars of historical data from {latest_file}")
                except Exception as e:
                    logger.warning(f"[{symbol}] Could not load historical data from {latest_file}: {e}")

            primary_data = RakutenData(
                dataname=hist_df,
                bridge=connector,
                symbol=symbol,
                timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
                compression=short_tf_config['compression']
            )
            cerebro.adddata(primary_data, name=str(symbol))

            # 3. リサンプリングデータを追加
            for tf_name in ['medium', 'long']:
                if tf_config := strategy_params['timeframes'].get(tf_name):
                    cerebro.resampledata(
                        primary_data,
                        timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']),
                        compression=tf_config['compression'],
                        name=tf_name
                    )
            
            # 4. ストラテジーを追加
            cerebro.addstrategy(RealTradeStrategy, strategy_params=strategy_params, strategy_components={})
            
            logger.info(f"[{symbol}] Cerebro instance created successfully with strategy '{strategy_name}'.")
            return cerebro

        except Exception as e:
            logger.error(f"[{symbol}] Failed to create Cerebro instance: {e}", exc_info=True)
            return None