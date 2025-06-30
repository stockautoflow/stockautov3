from realtrade.data_fetcher import DataFetcher
import backtrader as bt
import pandas as pd
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)

class RealtimeDataFeed(bt.feeds.PandasData):
    pass

class MockDataFetcher(DataFetcher):
    def start(self): 
        logger.info("MockDataFetcher: 起動しました。")
    
    def stop(self): 
        logger.info("MockDataFetcher: 停止しました。")

    def get_data_feed(self, symbol):
        if self.data_feeds.get(symbol) is None:
            df = self._generate_dummy_data(symbol, 200)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]

    def _generate_dummy_data(self, symbol, period):
        logger.info(f"MockDataFetcher: ダミー履歴データ生成 - 銘柄:{symbol}, 期間:{period}本")
        dates = pd.date_range(end=datetime.now(), periods=period, freq='1min').tz_localize(None)
        start_price, prices = np.random.uniform(1000, 5000), []
        current_price = start_price
        for _ in range(period):
            current_price *= (1 + np.random.normal(loc=0.0001, scale=0.01))
            prices.append(current_price)
        
        df = pd.DataFrame(index=dates)
        df['open'] = prices
        df['close'] = [p * (1 + np.random.normal(0, 0.005)) for p in prices]
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.005, size=period))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.005, size=period))
        df['volume'] = np.random.randint(100, 10000, size=period)
        return df