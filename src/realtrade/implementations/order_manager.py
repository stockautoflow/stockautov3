import logging
from src.core.strategy.order_manager import BaseOrderManager

logger = logging.getLogger(__name__)

class RealTradeOrderManager(BaseOrderManager):
    """
    リアルタイムトレード用の注文マネージャ。
    """
    def __init__(self, strategy, params, method, event_handler, statistics=None):
        # BaseOrderManager.__init__の引数に合わせて呼び出す
        # statisticsはリアルタイムのみで使用
        super().__init__(strategy, params, method, event_handler, statistics=statistics)