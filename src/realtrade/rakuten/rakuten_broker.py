import backtrader as bt
import logging

logger = logging.getLogger(__name__)

class RakutenBroker(bt.brokers.BackBroker):

    def __init__(self, bridge=None, **kwargs):
        super(RakutenBroker, self).__init__(**kwargs)
        if not bridge:
            raise ValueError("ExcelBridgeインスタンスが渡されていません。")
        self.bridge = bridge

    def getcash(self):
        cash = self.bridge.get_cash()
        self.cash = cash if cash is not None else self.cash
        return self.cash

    def buy(self, owner, data, size, price=None, plimit=None, **kwargs):
        logger.info(f"【手動発注モード】買いシグナル発生。自動発注は行いません。")
        order = super().buy(owner, data, size, price, plimit, **kwargs)
        return order

    def sell(self, owner, data, size, price=None, plimit=None, **kwargs):
        logger.info(f"【手動発注モード】売りシグナル発生。自動発注は行いません。")
        order = super().sell(owner, data, size, price, plimit, **kwargs)
        return order

    def cancel(self, order, **kwargs):
        logger.info(f"【手動発注モード】注文キャンセル。")
        return super().cancel(order, **kwargs)