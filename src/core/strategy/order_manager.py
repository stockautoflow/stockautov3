class BaseOrderManager:
    # [リファクタリング v2.0]
    # エントリー注文のサイズ計算や発注など、モード共通のロジックを提供する基底クラス。
    # 'method' に基づき、リスクベース方式とケリー基準方式を切り替える。
    
    # === ▼▼▼ v2.0 変更 (1/2) : __init__ ▼▼▼ ===
    def __init__(self, strategy, sizing_params, method: str, event_handler, statistics=None):
        # Args:
        #     strategy (BaseStrategy): ストラテジー本体
        #     sizing_params (dict): configの 'sizing' ブロック全体
        #     method (str): 解決済みの方式 ('risk_based' or 'kelly_criterion')
        #     event_handler (BaseEventHandler): イベントハンドラ
        #     statistics (dict, optional): ケリー基準値 (f値) を含む統計辞書
        self.strategy = strategy
        self.sizing_params = sizing_params # sizing_params 全体は引き続き保持
        self.method = method # 実行コンテキストで解決済みの method 文字列
        self.event_handler = event_handler
        self.statistics = statistics if statistics else {}
    # === ▲▲▲ v2.0 変更 (1/2) ▲▲▲ ===


    # === ▼▼▼ v2.0 変更 (2/2) : place_entry_order ▼▼▼ ===
    def place_entry_order(self, trade_type, reason, indicators):
        # [改修] リスクベース方式とケリー基準方式を切り替えてエントリー注文を発注する。
        exit_signal_generator = self.strategy.exit_signal_generator
        entry_price = self.strategy.datas[0].close[0]
        is_long = trade_type == 'long'
        
        # 1. 決済価格と1株あたりリスクを計算 (両方式で必要)
        exit_signal_generator.calculate_and_set_exit_prices(entry_price, is_long)
        risk_per_share = exit_signal_generator.risk_per_share

        # self.method は __init__ で渡された解決済みの方式
        method = self.method 

        # 1株あたりリスクが0の場合、リスクベース方式は使えない
        if risk_per_share < 1e-9 and method == 'risk_based':
            self.strategy.logger.log("リスクベース方式が選択されていますが、計算されたリスクが0のためエントリーをスキップ。")
            return

        cash = self.strategy.broker.getcash()
        max_investment = self.sizing_params.get('max_investment_per_trade', 1e7)
        
        size1 = 0.0 # 方式に基づいて計算されるサイズ

        # --- サイジング方式の分岐 ---
        
        if method == 'risk_based':
            # === (A) リスクベース方式 ===
            risk_params = self.sizing_params.get('risk_based', {})
            risk_per_trade_pct = risk_params.get('risk_per_trade', 0.01)
            risk_capital = cash * risk_per_trade_pct
            
            size1 = risk_capital / risk_per_share
            self.strategy.logger.log(f"サイジング (リスクベース): 資金={cash:,.0f}, リスク許容={risk_capital:,.0f} (1株リスク={risk_per_share:,.1f}) -> size1={size1:,.2f}")

        elif method == 'kelly_criterion':
            # === (B) ケリー基準方式 ===
            kelly_params = self.sizing_params.get('kelly_criterion', {})
            f_source = kelly_params.get('f_value_source', 'adjusted')
            max_f_value_cap = kelly_params.get('max_f_value_cap', 0.25)
            f_value = 0.0 # 決定された投資比率 (f値)
            
            if f_source == 'fixed':
                f_value = kelly_params.get('fixed_f_value', 0.1)
                self.strategy.logger.log(f"ケリー基準 (固定f値): f={f_value:.4f}")

            elif not self.statistics:
                # 統計情報なし (主にバックテスト時)
                self.strategy.logger.log(f"ケリー基準: '{f_source}' が選択されましたが、統計情報(statistics)がありません。f=0として処理します。")
                f_value = 0.0
            
            elif f_source == 'adjusted':
                try: f_value = float(self.statistics.get('Kelly_Adj', 0.0))
                except (ValueError, TypeError): f_value = 0.0
                self.strategy.logger.log(f"ケリー基準 (調整済): 統計 'Kelly_Adj'={self.statistics.get('Kelly_Adj')} -> f={f_value:.4f}")

            elif f_source == 'raw':
                try: f_value = float(self.statistics.get('Kelly_Raw', 0.0))
                except (ValueError, TypeError): f_value = 0.0
                if f_value < 0: f_value = 0.0 # マイナスf値は0に丸める
                self.strategy.logger.log(f"ケリー基準 (生): 統計 'Kelly_Raw'={self.statistics.get('Kelly_Raw')} -> f={f_value:.4f}")

            else:
                self.strategy.logger.log(f"警告: 不明なケリー方式 '{f_source}'。f=0でスキップします。")
                f_value = 0.0

            # f値の上限を適用 (Fractional Kelly)
            if f_value > max_f_value_cap:
                self.strategy.logger.log(f"ケリー基準: f値 {f_value:.4f} が上限 {max_f_value_cap:.4f} を超えたため調整。")
                f_value = max_f_value_cap

            if f_value <= 0:
                if f_value < 0: self.strategy.logger.log(f"ケリー基準: f値がマイナス ({f_value:.4f}) のためエントリーをスキップ。")
                return

            investment_capital = cash * f_value # 投資額（円）
            
            if entry_price > 0:
                size1 = investment_capital / entry_price
                self.strategy.logger.log(f"サイジング (ケリー基準): 資金={cash:,.0f}, f値={f_value:.4f}, 投資額={investment_capital:,.0f} (株価={entry_price:,.1f}) -> size1={size1:,.2f}")
            else:
                self.strategy.logger.log("ケリー基準: 株価が0のためスキップ。")
                return
        
        else:
            self.strategy.logger.log(f"警告: 不明なサイジング方式 '{method}'。エントリーをスキップします。")
            return

        # --- 共通の制約を適用 ---
        if entry_price <= 0: 
            self.strategy.logger.log(f"サイジング: エントリー価格が0のためスキップ。")
            return

        # (Size 2) 最大投資額ベースのサイズ
        size2 = max_investment / entry_price
        self.strategy.logger.log(f"サイジング (制約): 最大投資額={max_investment:,.0f} (株価={entry_price:,.1f}) -> size2={size2:,.2f}")
        
        # (最終数量) (リスクベース or ケリー基準) と (最大投資額) の小さい方を採用
        size = min(size1, size2)
        self.strategy.logger.log(f"サイジング (最終): min(size1, size2) -> 最終数量={size:,.2f}")

        if size <= 0: return

        self.strategy.entry_order = self.strategy.buy(size=size) if is_long else self.strategy.sell(size=size)

        # イベントハンドラ呼び出し (変更なし)
        self.event_handler.on_entry_order_placed(
            trade_type=trade_type, size=size, reason=reason,
            entry_price=entry_price,
            tp_price=exit_signal_generator.tp_price, sl_price=exit_signal_generator.sl_price
        )
    # === ▲▲▲ v2.0 変更 (2/2) ▲▲▲ ===

    def close_position(self):
        self.strategy.exit_orders.append(self.strategy.close())