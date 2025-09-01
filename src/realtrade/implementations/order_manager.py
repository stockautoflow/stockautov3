from src.core.strategy.order_manager import BaseOrderManager

class RealTradeOrderManager(BaseOrderManager):
    """
    [リファクタリング - 実装]
    リアルタイム取引用の注文管理。
    現時点では基底クラスの振る舞いと同じ。
    将来的にブローカーAPIを直接叩く場合はここに実装する。
    """
    pass