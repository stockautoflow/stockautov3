import backtrader as bt
import abc

class BrokerBridge(bt.broker.BrokerBase, metaclass=abc.ABCMeta):
    """
    証券会社APIと連携するための抽象基底クラス。
    backtraderのBrokerBaseを継承します。
    """
    @abc.abstractmethod
    def get_cash(self):
        """利用可能な現金額を取得します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def get_position(self, data, clone=True):
        """指定された銘柄のポジションを取得します。"""
        raise NotImplementedError

    # place_order, cancel_order などのメソッドも後続ステップで定義