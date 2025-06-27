import backtrader as bt
from enum import Enum
from backtrader.position import Position

class OrderStatus(Enum):
    SUBMITTED = 'submitted'; ACCEPTED = 'accepted'; PARTIALLY_FILLED = 'partially_filled'; FILLED = 'filled'; CANCELED = 'canceled'; REJECTED = 'rejected'; EXPIRED = 'expired'

class BrokerBridge(bt.broker.BrokerBase):
    """
    証券会社APIと連携するためのインターフェース（基底クラス）。
    """
    Position = Position

    def __init__(self, config):
        super(BrokerBridge, self).__init__()
        self.config = config
        self.notification_queue = []
        # [追加] backtraderが要求する属性を初期化
        self.startingcash = 0.0

    def start(self): raise NotImplementedError
    def stop(self): raise NotImplementedError
    def getcash(self): raise NotImplementedError
    def getposition(self, data, clone=True): raise NotImplementedError
    def getvalue(self, datas=None): raise NotImplementedError
    def place_order(self, order): raise NotImplementedError
    def cancel_order(self, order): raise NotImplementedError
    def poll_orders(self): raise NotImplementedError
    def get_notification(self):
        if self.notification_queue:
            return self.notification_queue.pop(0)
        return None