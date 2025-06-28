from realtrade.data_fetcher import DataFetcher, RealtimeDataFeed
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MockDataFetcher(DataFetcher):
    def start(self):
        logger.info("MockDataFetcher: 起動しました。")

    def stop(self):
        logger.info("MockDataFetcher: 停止しました。")

    def get_data_feed(self, symbol):
        if self.data_feeds.get(symbol) is None:
            df = self.fetch_historical_data(symbol, 'minutes', 1, 200)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]

    def fetch_historical_data(self, symbol, timeframe, compression, period):
        logger.info(f"MockDataFetcher: 履歴データリクエスト受信 - 銘柄:{symbol}, 期間:{period}本")
        end_date = datetime.now()
        dates = pd.date_range(end=end_date, periods=period, freq=f'{compression}min').tz_localize(None)
        
        start_price = np.random.uniform(1000, 5000)
        returns = np.random.normal(loc=0.0001, scale=0.01, size=period)
        prices = start_price * (1 + returns).cumprod()
        
        df = pd.DataFrame(index=dates)
        df['open'] = prices
        df['high'] = prices * (1 + np.random.uniform(0, 0.01, size=period))
        df['low'] = prices * (1 - np.random.uniform(0, 0.01, size=period))
        df['close'] = prices * (1 + np.random.normal(loc=0, scale=0.005, size=period))
        
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.005, size=period))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.005, size=period))
        
        df['volume'] = np.random.randint(100, 10000, size=period)
        df.columns = [col.lower() for col in df.columns]
        
        return df