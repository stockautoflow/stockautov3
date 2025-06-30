import abc
import backtrader as bt

class DataFetcher(metaclass=abc.ABCMeta):
    def __init__(self, symbols, config):
        self.symbols = symbols
        self.config = config
        self.data_feeds = {s: None for s in symbols}

    @abc.abstractmethod
    def start(self): raise NotImplementedError
    @abc.abstractmethod
    def stop(self): raise NotImplementedError
    @abc.abstractmethod
    def get_data_feed(self, symbol): raise NotImplementedError