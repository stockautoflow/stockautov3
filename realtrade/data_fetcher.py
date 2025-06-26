import backtrader as bt
import abc

class DataFetcher(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def start(self):
        raise NotImplementedError
    @abc.abstractmethod
    def stop(self):
        raise NotImplementedError
    @abc.abstractmethod
    def get_data_feed(self, symbol):
        raise NotImplementedError
    @abc.abstractmethod
    def fetch_historical_data(self, symbol, period, timeframe):
        raise NotImplementedError