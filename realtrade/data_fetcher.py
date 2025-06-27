import backtrader as bt
import abc
import pandas as pd
from datetime import datetime, timedelta

class RealtimeDataFeed(bt.feeds.PandasData):
    def push_data(self, data_dict):
        # 現時点では未実装
        pass

class DataFetcher(metaclass=abc.ABCMeta):
    def __init__(self, symbols, config):
        self.symbols = symbols; self.config = config; self.data_feeds = {s: None for s in symbols}
    @abc.abstractmethod
    def start(self): raise NotImplementedError
    @abc.abstractmethod
    def stop(self): raise NotImplementedError
    @abc.abstractmethod
    def get_data_feed(self, symbol): raise NotImplementedError
    @abc.abstractmethod
    def fetch_historical_data(self, symbol, timeframe, compression, period): raise NotImplementedError