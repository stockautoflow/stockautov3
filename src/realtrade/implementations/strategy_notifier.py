import logging
from datetime import datetime, timedelta
from src.core.util import notifier
from src.core.strategy.strategy_notifier import BaseStrategyNotifier

class RealTradeStrategyNotifier(BaseStrategyNotifier):
    
    def __init__(self, strategy):
        super().__init__(strategy)
        self.logger = logging.getLogger(self.__class__.__name__)

    def send(self, subject, body, immediate=False):
        
        # 5.1. 履歴データ再生中の判定 (全通知に適用)
        if not getattr(self.strategy, 'realtime_phase_started', False):
            self.logger.debug(f"履歴データ供給中のため通知を抑制: {subject}")
            return
        
        try:
            bar_datetime = self.strategy.data0.datetime.datetime(0)
        except IndexError:
            # バーがまだ存在しない（start()時など）場合は、比較せずそのまま送信試行
            self.logger.warning(f"バーデータが存在しないため、時間差チェックをスキップ: {subject}")
            notifier.send_email(subject, body, immediate=immediate)
            return

        if bar_datetime.tzinfo is not None:
            bar_datetime = bar_datetime.replace(tzinfo=None)

        current_time = datetime.now()
        allowed_delay = timedelta(minutes=15) # 異常遅延とみなす閾値
        time_diff = current_time - bar_datetime
        is_delayed = time_diff > allowed_delay

        # 5.3. 警告の追記
        if is_delayed:
            delay_minutes = int(time_diff.total_seconds() / 60)
            
            # 決済通知 (件名に "決済" や "Stop Loss" を含む) かどうかで警告レベルを変更
            if "決済" in subject or "Stop Loss" in subject:
                subject = f"【!!!決済遅延警告: {delay_minutes}分前!!!】{subject}"
            else:
                subject = f"【エントリー遅延警告: {delay_minutes}分前】{subject}"
            
            # --- ここを修正 (f-stringの連結 -> f"""...""") ---
            warning_msg = f"""警告: このシグナルは {delay_minutes}分前 ({bar_datetime.isoformat()}) のデータに基づいています。
現在の価格と乖離している可能性があります。
------------------------------------

"""
            body = warning_msg + body
        
        # 5.4. 通知の実行
        self.logger.debug(f"通知リクエストを発行: {subject}")
        notifier.send_email(subject, body, immediate=immediate)