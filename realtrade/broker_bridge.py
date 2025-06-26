import backtrader as bt
import abc

class BrokerBridge(bt.broker.BrokerBase, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_cash(self):
        raise NotImplementedError
    @abc.abstractmethod
    def get_position(self, data, clone=True):
        raise NotImplementedError