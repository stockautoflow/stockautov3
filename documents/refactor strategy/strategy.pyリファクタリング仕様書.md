ご指定のスクリプト名に基づき、リファクタリングの仕様書を作成します。この仕様書は、各モジュールの責務と機能、そしてシステム全体での連携方法を明確にします。

### 1. プロジェクト全体のリファクタリング方針

本リファクタリングは、肥大化した`strategy.py`の責務を分解し、**単一責務の原則**に基づいたモジュール設計を確立します。これにより、コードの再利用性を高め、保守性・拡張性を向上させます。

---

### 2. 各スクリプトの役割と機能詳細

#### `strategy.py`

このスクリプトは、Backtraderの`bt.Strategy`を継承する**オーケストレーター**としての役割を担います。取引ロジック自体は持たず、他のモジュールを呼び出して取引フロー全体を管理します。

* **役割**: Backtraderのイベント（`__init__`, `next`, `notify_order`など）をトリガーとして、専門的なモジュールを呼び出すハブとなる。
* **主な機能**:
    * **`__init__`**: `strategy_initializer.py`を呼び出し、戦略を動的に設定する。
    * **`next`**: `trade_evaluator.py`の判断に従い、`order_executor.py`や`position_manager.py`を呼び出し、取引判断と注文実行を管理する。
    * **`notify_order`**: `notification_manager.py`を呼び出し、注文イベントを処理する。

---

#### `src/core/strategy_initializer.py`

戦略の初期化と設定を専門に扱います。

* **役割**: 外部のYAML設定ファイルに基づき、`strategy.py`インスタンスに動的な設定を注入する。
* **主な機能**:
    * **設定のロード**: `strategy_base.yml`と`strategy_catalog.yml`を読み込み、戦略パラメータを統合する。
    * **インジケーターの生成**: 戦略定義に含まれるすべてのインジケーター（カスタムインジケーターを含む）を動的に生成し、`strategy`インスタンスにアタッチする。
    * **状態の設定**: `live_trading`フラグや、DBからロードされた`persisted_position`情報に基づいて、戦略の内部状態を設定する。

---

#### `src/core/trade_evaluator.py`

取引判断の純粋なロジックを担います。

* **役割**: エントリーおよびエグジットの条件を評価し、取引のシグナルを生成する。
* **主な機能**:
    * **`evaluate_entry_conditions(conditions, data_feeds, indicators)`**: エントリー条件のリストをすべて評価し、満たされた場合に`True`を返す。
    * **`evaluate_exit_conditions(position, current_price, strategy_params)`**: 利確と損切りの条件を評価し、ポジションを決済すべきかを判断する。
* **設計思想**: エントリーとエグジットの評価は密接に関連しているため、単一のファイルに統合し、コードの追跡を簡潔に保つ。

---

#### `src/core/order_executor.py`

注文の発注と執行を専門に扱います。

* **役割**: 取引の判断に基づき、注文数量を計算し、`bt.Strategy`を介して注文を執行する。
* **主な機能**:
    * **`place_entry_order(strategy, trade_type, reason)`**: 資金管理ルール（`sizing`）に従い注文数量を計算し、エントリー注文を発注する。
    * **`place_exit_orders(strategy, live_trading)`**: 決済注文を発注する。バックテストモードではネイティブなOCO注文、ライブモードでは手動監視ロジックを呼び出す。

---

#### `src/core/position_manager.py`

ポジション情報の管理と状態の復元を専門に扱います。

* **役割**: `strategy.position`からポジション情報を読み取り、その状態を管理・更新する。
* **主な機能**:
    * **`update_state(strategy)`**: `strategy.position`から現在のポジション情報を取得し、必要に応じてデータベースへの書き込みを指示する。
    * **`restore_state(strategy, persisted_position)`**: データベースからロードされたポジション情報を使用して、戦略の内部状態（ポジションサイズ、価格など）を復元する。

---

#### `src/core/notification_manager.py`

取引イベントの通知とロギングを専門に扱います。

* **役割**: 注文や取引の重要なイベントを検知し、ログ記録やメール通知をトリガーする。
* **主な機能**:
    * **`handle_order_notification(order, live_trading, data_feed, notifier)`**: `notify_order`イベントから呼び出され、約定や注文失敗などのステータスを処理し、ログを生成する。
    * **`log_trade_event(trade, logger)`**: トレードの開始・終了イベントを詳細にログに記録する。
* **連携**: `notifier.py`を介してメール送信を非同期で実行し、Gmailのレート制限を回避する。