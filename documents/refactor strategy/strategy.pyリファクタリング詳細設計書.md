### 戦略モジュール詳細設計書

この設計書は、リファクタリング後の戦略モジュール群の具体的な実装方法を定義します。各スクリプトは、単一責務の原則に基づいて機能が分離されています。

---

### 1. `strategy.py`

このファイルは、Backtraderの**`bt.Strategy`クラス**を継承し、各専門モジュールを統合する**オーケストレーター（指揮者）**として機能します。

#### クラス: `DynamicStrategy`

* **属性**:
    * `strategy_params`: 戦略の全パラメータを保持する辞書。
    * `live_trading`: リアルタイム取引モードかを示す真偽値。
    * `entry_reason`: エントリーの根拠を文字列で記録。
    * `tp_price`, `sl_price`: 決済価格を保持。
    * `indicators`: 動的に生成された全インジケーターの参照を保持する辞書。
* **メソッド**:
    * `__init__()`:
        * `strategy_initializer.py`の関数を呼び出し、`strategy_params`と`indicators`を初期化する.
        * `live_trading`フラグを設定する.
    * `next()`:
        * 現在のポジションがない場合、`trade_evaluator.py`を呼び出してエントリー条件を評価する.
        * エントリー条件が満たされた場合、`order_executor.py`を呼び出して注文を発注する.
        * ポジションがある場合、`trade_evaluator.py`を呼び出して決済条件を評価する.
        * ライブモードの場合、決済条件が満たされたら`order_executor.py`を呼び出して決済注文を発注する.
    * `notify_order(order)`:
        * `notification_manager.py`を呼び出し、注文ステータス（約定、キャンセルなど）に応じたログ記録と通知処理を実行する.
    * `notify_trade(trade)`:
        * `position_manager.py`を呼び出し、ポジションの開始・終了イベントをDBに記録する.

---

### 2. `src/core/strategy_initializer.py`

戦略の初期化を担う、独立したヘルパースクリプトです。

* **役割**: `DynamicStrategy`クラスの初期化プロセスを外部化する。
* **関数**:
    * `initialize(strategy)`:
        * 戦略カタログ (`strategy_catalog.yml`) とベース設定 (`strategy_base.yml`) を読み込む.
        * `strategy_params`辞書を構築し、`strategy`オブジェクトに割り当てる.
        * `create_indicators(strategy_params)`関数を呼び出し、インジケーター辞書を生成して返す.
    * `create_indicators(strategy_params)`:
        * 戦略定義内のすべての`indicator`、`indicator1`、`indicator2`を走査する.
        * 各インジケーター定義から、対応するBacktraderのクラス（`bt.indicators.EMA`, `VWAP`など）を見つける.
        * クラスとパラメータからインジケーターインスタンスを生成し、一意なキーで辞書に格納して返す.

---

### 3. `src/core/trade_evaluator.py`

取引シグナルの評価ロジックをカプセル化します。

* **役割**: エントリーとエグジットの条件評価ロジックを集中管理する.
* **関数**:
    * `check_entry_conditions(conditions, data_feeds, indicators)`:
        * 入力された**`conditions`リスト**をループし、すべての条件が満たされるか検証する.
        * 内部ヘルパー関数`_evaluate_single_condition()`を呼び出し、個々の条件を評価する。
        * すべての条件が`True`であれば`True`を返し、そうでなければ`False`を返す.
    * `check_exit_conditions(position, current_price, strategy_params)`:
        * 利確条件（`atr_multiple`）と損切り条件（`atr_stoptrail`）を評価する.
        * 利確価格と損切り価格を動的に計算する.
        * 決済が必要な場合に`True`を返す。
    * `_evaluate_single_condition(condition, data_feeds, indicators)`:
        * 条件の`type`（`crossover`、`compare`など）に応じて、適切な比較ロジックを実行する.
        * インジケーターの値、データライン（`close`など）、固定値のいずれかを比較対象として使用する.

---

### 4. `src/core/order_executor.py`

注文の計算と執行ロジックを分離します。

* **役割**: `trade_evaluator.py`の判断に従って、注文を正確に計算し、発注する.
* **関数**:
    * `place_entry_order(strategy, trade_type, reason)`:
        * リスクベースの資金管理（`risk_per_trade`）と最大投資額（`max_investment_per_trade`）に基づいて注文数量を計算する.
        * `strategy.buy()`または`strategy.sell()`を呼び出して注文を発注する.
    * `place_exit_orders(strategy, live_trading)`:
        * `strategy`の`close()`メソッドを呼び出し、ポジションを決済する注文を発注する.
        * バックテストモードでは`bt.Order.StopTrail`や`bt.Order.Limit`を使用する.

---

### 5. `src/core/position_manager.py`

ポジション情報の永続化と復元を管理します。

* **役割**: `run_realtrade.py`が起動時に呼び出し、永続化されたポジション情報を戦略に復元する.
* **関数**:
    * `restore_state(strategy, persisted_position)`:
        * `persisted_position`辞書からポジションサイズと価格を読み込む.
        * `strategy`インスタンスの`position.size`と`position.price`を更新する.
        * 利確/損切り価格を再計算し、`strategy`インスタンスに設定する.

---

### 6. `src/core/notification_manager.py`

ログ記録とメール通知を一元的に処理します。

* **役割**: 取引の重要なライフサイクルイベントをログに記録し、リアルタイムモードでは非同期でメール通知を送信する.
* **関数**:
    * `handle_order_notification(order, live_trading, data_feed, notifier)`:
        * 注文ステータス（`Completed`, `Canceled`など）を解析し、ログメッセージを生成する.
        * `live_trading`が`True`の場合、`notifier.send_email()`を呼び出し、通知キューにメッセージを追加する.
    * `log_trade_event(trade, logger)`:
        * `trade`イベント（`isopen`, `isclosed`）に基づいて、トレードの詳細（PNL、手数料など）をログに記録する.