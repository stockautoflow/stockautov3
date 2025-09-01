class BaseStrategyNotifier:
    """
    [リファクタリング]
    通知機能のインターフェースを定義する基底クラス。
    """
    def __init__(self, strategy):
        self.strategy = strategy

    def send(self, subject, body, immediate=False):
        """[抽象メソッド] 通知を送信する方法"""
        raise NotImplementedError