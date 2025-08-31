import backtrader as bt

class EventHandler:
    """
    責務：Backtraderからのイベントを解釈し、情報（メッセージ）を整形して、
    ロガーやノーティファイアーに渡す。
    """
    def __init__(self, strategy, logger, notifier, state_manager=None):
        self.strategy = strategy
        self.logger = logger
        self.notifier = notifier
        self.state_manager = state_manager
        self.current_entry_reason = "" # notify_tradeで参照するため

    def on_entry_order_placed(self, trade_type, size, reason, tp_price, sl_price):
        """エントリー注文が発注された際のログ記録と通知"""
        self.current_entry_reason = reason
        is_long = trade_type == 'long'
        
        self.logger.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, TP: {tp_price:.2f}, SL: {sl_price:.2f}")
        
        subject = f"【リアルタイム取引】新規注文発注 ({self.strategy.data0._name})"
        body = (
            f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\n"
            f"銘柄: {self.strategy.data0._name}\n"
            f"戦略: {self.strategy.p.strategy_params.get('name', 'N/A')}\n"
            f"方向: {'BUY' if is_long else 'SELL'}\n"
            f"数量: {size:.2f}\n\n"
            "--- エントリー根拠 ---\n"
            f"{reason}"
        )
        self.notifier.send(subject, body, immediate=True)

    def on_order_update(self, order):
        """注文状態が更新された際のログ記録と通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        is_entry = self.strategy.entry_order and self.strategy.entry_order.ref == order.ref
        is_exit = any(o.ref == order.ref for o in self.strategy.exit_orders)

        if not is_entry and not is_exit:
            return

        if order.status == order.Completed:
            if is_entry:
                self._handle_entry_completion(order)
            elif is_exit:
                self._handle_exit_completion(order)
            
            self._update_trade_persistence(order)
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self._handle_order_failure(order)

        # 注文オブジェクトへの参照をクリア
        if is_entry: self.strategy.entry_order = None
        if is_exit: self.strategy.exit_orders = []

    def _handle_entry_completion(self, order):
        """エントリー注文が約定した際の処理"""
        self.logger.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
        
        subject = f"【リアルタイム取引】エントリー注文約定 ({self.strategy.data0._name})"
        body = (
            f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\n"
            f"銘柄: {self.strategy.data0._name}\n"
            f"ステータス: {order.getstatusname()}\n"
            f"方向: {'BUY' if order.isbuy() else 'SELL'}\n"
            f"約定数量: {order.executed.size:.2f}\n"
            f"約定価格: {order.executed.price:.2f}"
        )
        self.notifier.send(subject, body, immediate=True)

        # バックテストの場合は、ここで決済注文を発注
        if not self.strategy.p.live_trading:
            self.strategy.order_manager.place_backtest_exit_orders()
        else:
            # ライブの場合は、決済価格を再計算・設定
            self.strategy.exit_signal_generator.calculate_and_set_exit_prices(
                entry_price=order.executed.price,
                is_long=order.isbuy()
            )
            esg = self.strategy.exit_signal_generator
            self.logger.log(f"ライブモード決済監視開始: TP={esg.tp_price:.2f}, Initial SL={esg.sl_price:.2f}")


    def _handle_exit_completion(self, order):
        """決済注文が約定した際の処理"""
        pnl = order.executed.pnl
        exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
        
        self.logger.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}")
        
        subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.strategy.data0._name})"
        body = (
            f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\n"
            f"銘柄: {self.strategy.data0._name}\n"
            f"ステータス: {order.getstatusname()} ({exit_reason})\n"
            f"決済数量: {order.executed.size:.2f}\n"
            f"実現損益: {pnl:,.2f}"
        )
        self.notifier.send(subject, body, immediate=True)
        
        # 決済価格をリセット
        esg = self.strategy.exit_signal_generator
        esg.tp_price, esg.sl_price = 0.0, 0.0

    def _handle_order_failure(self, order):
        """注文が失敗・キャンセルされた際の処理"""
        self.logger.log(f"注文失敗/キャンセル: {order.getstatusname()}")

        subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.strategy.data0._name})"
        body = (f"日時: {self.strategy.data.datetime.datetime(0).isoformat()}\n"
                f"銘柄: {self.strategy.data0._name}\n"
                f"ステータス: {order.getstatusname()}")
        self.notifier.send(subject, body, immediate=True)
        
        # エントリー注文失敗時は決済価格をリセット
        is_entry = self.strategy.entry_order and self.strategy.entry_order.ref == order.ref
        if is_entry:
            esg = self.strategy.exit_signal_generator
            esg.tp_price, esg.sl_price = 0.0, 0.0

    def _update_trade_persistence(self, order):
        """
        リアルタイム取引時に、DBへポジションの状態を永続化する。
        (旧 TradePersistenceAnalyzer の役割)
        """
        if not self.strategy.p.live_trading or not self.state_manager:
            return

        symbol = order.data._name
        position = self.strategy.broker.getposition(order.data)

        if position.size == 0:
            # ポジションが決済された場合
            self.state_manager.delete_position(symbol)
            self.logger.log(f"StateManager: ポジションをDBから削除: {symbol}")
        else:
            # ポジションが新規作成/変更された場合
            entry_dt = bt.num2date(order.executed.dt).isoformat()
            self.state_manager.save_position(symbol, position.size, position.price, entry_dt)
            self.logger.log(f"StateManager: ポジションをDBに保存/更新: {symbol} (Size: {position.size})")