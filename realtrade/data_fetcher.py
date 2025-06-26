import backtrader as bt
import abc

class DataFetcher(metaclass=abc.ABCMeta):
    """
    証券会社APIから価格データを取得するための抽象基底クラス。
    """
    @abc.abstractmethod
    def start(self):
        """データ取得を開始します (WebSocket接続など)。"""
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        """データ取得を停止します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def get_data_feed(self, symbol):
        """指定された銘柄のデータフィードオブジェクトを返します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_historical_data(self, symbol, period, timeframe):
        """戦略の初期化に必要な過去のデータを取得します。"""
        raise NotImplementedError