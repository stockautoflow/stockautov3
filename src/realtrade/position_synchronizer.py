import threading
import time
import logging

logger = logging.getLogger(__name__)

class PositionSynchronizer(threading.Thread):
    """
    外部(Excel)と内部(システム)のポジションを同期させる責務を持つ。
    threading.Threadを継承し、独立したスレッドで動作する。
    """
    SYNC_INTERVAL = 1.0 # 1秒ごとに同期

    def __init__(self, connector, strategies, stop_event, **kwargs):
        super().__init__(daemon=True, name="PositionSyncThread", **kwargs)
        self.connector = connector
        self.strategies = strategies # {symbol: strategy_instance}
        self.stop_event = stop_event
        logger.info("PositionSynchronizer initialized.")

    def run(self):
        """スレッドのメインループ。定期的に同期処理を実行する。"""
        logger.info("Position synchronization thread started.")
        while not self.stop_event.is_set():
            try:
                # 外部(Excel)のポジションを取得
                excel_positions = self.connector.get_positions()

                # 内部(ストラテジー)のポジションを収集
                internal_positions = {}
                # スレッドセーフなアクセスのため、辞書のコピーを作成
                strategies_copy = self.strategies.copy()
                for symbol, strategy in strategies_copy.items():
                    if hasattr(strategy, 'realtime_phase_started') and strategy.realtime_phase_started and strategy.position:
                        internal_positions[symbol] = {
                            'size': strategy.position.size,
                            'price': strategy.position.price
                        }

                # 同期処理を実行
                self._sync_positions(excel_positions, internal_positions)
            
            except Exception as e:
                logger.error(f"Error in position synchronization loop: {e}", exc_info=True)

            time.sleep(self.SYNC_INTERVAL)
        logger.info("Position synchronization thread stopped.")

    def _sync_positions(self, excel_pos, internal_pos):
        """2つのポジション情報を比較し、差異があれば同期する。"""
        all_symbols = set(excel_pos.keys()) | set(internal_pos.keys())

        for symbol in all_symbols:
            strategy = self.strategies.get(symbol)
            if not strategy or not (hasattr(strategy, 'realtime_phase_started') and strategy.realtime_phase_started):
                continue

            e_pos = excel_pos.get(symbol)
            i_pos = internal_pos.get(symbol)

            if e_pos and not i_pos:
                # 新規検知: Excelにあり、内部にない -> 内部状態に注入
                logger.info(f"[{symbol}] New position detected. Injecting into strategy: {e_pos}")
                strategy.inject_position(e_pos['size'], e_pos['price'])
            
            elif not e_pos and i_pos:
                # 決済検知: 内部にあり、Excelにない -> 内部状態をクリア
                logger.info(f"[{symbol}] Closed position detected. Clearing strategy state.")
                strategy.force_close_position()

            elif e_pos and i_pos:
                # 差異検知: 両方に存在するが内容が異なる -> Excelの情報に更新
                if e_pos['size'] != i_pos['size'] or e_pos['price'] != i_pos['price']:
                    logger.info(f"[{symbol}] Position difference detected. Updating strategy: {e_pos}")
                    strategy.inject_position(e_pos['size'], e_pos['price'])