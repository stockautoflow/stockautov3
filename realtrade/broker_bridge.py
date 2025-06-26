import backtrader as bt
import abc
from enum import Enum

# 注文状態の管理をしやすくするためのEnum
class OrderStatus(Enum):
    SUBMITTED = 'submitted'
    ACCEPTED = 'accepted'
    PARTIALLY_FILLED = 'partially_filled'
    FILLED = 'filled'
    CANCELED = 'canceled'
    REJECTED = 'rejected'
    EXPIRED = 'expired'

class BrokerBridge(bt.broker.BrokerBase, metaclass=abc.ABCMeta):
    """
    証券会社APIと連携するためのインターフェース（抽象基底クラス）。
    このクラスを継承して、各証券会社専用のブリッジを実装します。
    """
    def __init__(self, config):
        super(BrokerBridge, self).__init__()
        self.config = config
        self.positions = {} # ポジション情報を保持する辞書

    @abc.abstractmethod
    def start(self):
        """ブローカーへの接続や初期化処理を行います。"""
        raise NotImplementedError

    @abc.abstractmethod
    def stop(self):
        """ブローカーとの接続を安全に終了します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def get_cash(self):
        """利用可能な現金額を取得します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def get_position(self, data, clone=True):
        """指定された銘柄のポジションサイズを取得します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def place_order(self, order):
        """
        backtraderから渡された注文オブジェクトを処理し、
        証券会社APIに発注リクエストを送信します。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def cancel_order(self, order):
        """注文のキャンセルリクエストを送信します。"""
        raise NotImplementedError

    @abc.abstractmethod
    def poll_orders(self):
        """
        未約定の注文の状態をAPIで確認し、変更があればbacktraderに
        通知 (notify_order) するためのロジックを実装します。
        メインループから定期的に呼び出されることを想定します。
        """
        raise NotImplementedError