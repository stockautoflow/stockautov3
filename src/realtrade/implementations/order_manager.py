from src.core.strategy.order_manager import BaseOrderManager

class RealTradeOrderManager(BaseOrderManager):
    # [リファクタリング - 実装 v2.0]
    # BaseOrderManager の新しい __init__ シグネチャに対応する。
    
    # === ▼▼▼ v2.0 変更: __init__ を追加 ▼▼▼ ===
    def __init__(self, strategy, sizing_params, method, event_handler, statistics=None):
        # BaseOrderManager の __init__ を呼び出す。
        # リアルタイム取引では statistics が渡される。
        super().__init__(strategy, sizing_params, method, event_handler, statistics=statistics)
    # === ▲▲▲ v2.0 変更 ▲▲▲ ===