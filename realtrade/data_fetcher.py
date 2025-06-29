# このファイルはシミュレーションモードでのみ使用されます。
# ライブトレーディングでは realtrade/live/sbi_data.py が使用されます。
import backtrader as bt
import abc
import pandas as pd
from datetime import datetime, timedelta

class RealtimeDataFeed(bt.feeds.PandasData):
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