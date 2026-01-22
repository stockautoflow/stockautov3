from src.core.strategy.exit_signal_generator import BaseExitSignalGenerator

class RealTradeExitSignalGenerator(BaseExitSignalGenerator):
    """
    リアルタイムトレード用の出口信号生成クラス。
    毎barの価格を監視し、決済条件(TP/SL)を判定する。
    トレーリングストップのロジックもここに実装される。
    """
    def __init__(self, strategy, order_manager):
        super().__init__(strategy, order_manager)

    def check_exit_conditions(self):
        """
        現在の価格とポジションを確認し、TP/SL条件に合致すれば決済注文を出す。
        """
        pos = self.strategy.getposition()
        # ポジションがない場合は何もしない
        if not pos or pos.size == 0:
            return

        is_long = pos.size > 0
        current_price = self.strategy.datas[0].close[0]
        logger = self.strategy.logger

        if is_long:
            # --- ロングポジションの場合 ---
            
            # 利確判定 (Take Profit)
            if self.tp_price != 0 and current_price >= self.tp_price:
                logger.log(f"ライブ: 利確条件ヒット(Long)。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
                self.order_manager.close_position()
                return

            # 損切り判定 (Stop Loss)
            if self.sl_price != 0:
                if current_price <= self.sl_price:
                    logger.log(f"ライブ: 損切り条件ヒット(Long)。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                    self.order_manager.close_position()
                    return
                
                # トレーリングストップの更新 (価格上昇に合わせてSLを引き上げる)
                # リスク幅(risk_per_share)を維持して追従
                if self.risk_per_share > 0:
                    new_sl_price = current_price - self.risk_per_share
                    if new_sl_price > self.sl_price:
                        logger.log(f"ライブ: SL価格を更新(Long) {self.sl_price:.2f} -> {new_sl_price:.2f}")
                        self.sl_price = new_sl_price
        else:
            # --- ショートポジションの場合 ---
            
            # 利確判定 (Take Profit)
            if self.tp_price != 0 and current_price <= self.tp_price:
                logger.log(f"ライブ: 利確条件ヒット(Short)。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}")
                self.order_manager.close_position()
                return

            # 損切り判定 (Stop Loss)
            if self.sl_price != 0:
                if current_price >= self.sl_price:
                    logger.log(f"ライブ: 損切り条件ヒット(Short)。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}")
                    self.order_manager.close_position()
                    return
                
                # トレーリングストップの更新 (価格下落に合わせてSLを引き下げる)
                if self.risk_per_share > 0:
                    new_sl_price = current_price + self.risk_per_share
                    if new_sl_price < self.sl_price:
                        logger.log(f"ライブ: SL価格を更新(Short) {self.sl_price:.2f} -> {new_sl_price:.2f}")
                        self.sl_price = new_sl_price