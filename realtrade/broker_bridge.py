import backtrader as bt
from enum import Enum

class OrderStatus(Enum):
    SUBMITTED = 'submitted'; ACCEPTED = 'accepted'; PARTIALLY_FILLED = 'partially_filled'; FILLED = 'filled'; CANCELED = 'canceled'; REJECTED = 'rejected'; EXPIRED = 'expired'

class BrokerBridge(bt.broker.BrokerBase):
    def __init__(self, config):
        super(BrokerBridge, self).__init__(); self.config = config; self.positions = {}
    def start(self): raise NotImplementedError
    def stop(self): raise NotImplementedError
    def get_cash(self): raise NotImplementedError
    def get_position(self, data, clone=True): raise NotImplementedError
    def place_order(self, order): raise NotImplementedError
    def cancel_order(self, order): raise NotImplementedError
    def poll_orders(self): raise NotImplementedError