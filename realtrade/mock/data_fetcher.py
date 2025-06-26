from realtrade.data_fetcher import DataFetcher, RealtimeDataFeed
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

class MockDataFetcher(DataFetcher):
    """
    ダミーの価格データを生成して返す模擬データフェッチャー。
    """
    def start(self):
        print("MockDataFetcher: 起動しました。")

    def stop(self):
        print("MockDataFetcher: 停止しました。")

    def get_data_feed(self, symbol):
        # ダミーのデータフィードを返す
        if self.data_feeds.get(symbol) is None:
            df = self.fetch_historical_data(symbol, 'minutes', 1, 100)
            self.data_feeds[symbol] = RealtimeDataFeed(dataname=df)
        return self.data_feeds[symbol]

    def fetch_historical_data(self, symbol, timeframe, compression, period):
        """ダミーのOHLCVデータをDataFrameで生成します。"""
        print(f"MockDataFetcher: 履歴データリクエスト受信 - 銘柄:{symbol}, 期間:{period}本")
        end_date = datetime.now()
        dates = pd.date_range(end=end_date, periods=period, freq=f'{compression}min')
        
        # ランダムウォークで価格データを生成
        start_price = np.random.uniform(1000, 5000)
        returns = np.random.normal(loc=0, scale=0.01, size=period)
        prices = start_price * (1 + returns).cumprod()

        data = {
            'open': prices,
            'high': prices * np.random.uniform(1, 1.02, size=period),
            'low': prices * np.random.uniform(0.98, 1, size=period),
            'close': prices * np.random.uniform(0.99, 1.01, size=period),
            'volume': np.random.randint(100, 10000, size=period)
        }
        df = pd.DataFrame(data, index=dates)
        # カラム名を小文字に統一
        df.columns = [col.lower() for col in df.columns]
        # open, high, low, closeを再計算して整合性を保つ
        df['open'] = df['close'].shift(1)
        df.loc[df.index[0], 'open'] = start_price
        df['high'] = df[['open', 'close']].max(axis=1) * 1.01
        df['low'] = df[['open', 'close']].min(axis=1) * 0.99

        return df