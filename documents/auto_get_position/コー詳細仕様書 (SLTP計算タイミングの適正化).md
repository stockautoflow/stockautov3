はい、承知いたしました。先の仕様検討に基づき、`aft`コードを修正するための詳細設計書を作成します。

-----

## **詳細設計書：SL/TP計算ロジック修正**

  - **バージョン**: 1.0
  - **作成日**: 2025年8月25日
  - **作成者**: Gemini
  - **対象モジュール**: `src.core.strategy.DynamicStrategy`

-----

### \#\# 1. 概要と目的

本設計書は、`DynamicStrategy`クラスにおける損切り（SL）・利確（TP）価格の計算タイミングを修正するための詳細な手順を定義する。

現在の実装では、バックテスト時にSL/TP価格がエントリー注文の**約定後**に計算されており、「先読みバイアス」を発生させ、テストの信頼性を損なう原因となっている。

本修正の目的は、SL/TP価格の計算をエントリー条件が成立した**シグナルバー**の時点で行うように変更し、バックテストの論理的整合性と再現性を確保することである。

-----

### \#\# 2. 現状（As-Is）のロジックフロー分析

現在のバックテストにおける処理フローには以下の欠陥が存在する。

1.  `check_entry_conditions`メソッドがシグナルバーでエントリーを決定し、`buy()`/`sell()`で注文を発注する。
2.  この時点では`self.sl_price`と`self.tp_price`は未計算（`0`）のままである。
3.  次のバーで注文が約定し、`notify_order`メソッドがトリガーされる。
4.  バックテスト用のロジックパス (`if not self.live_trading:`) が`place_native_exit_orders()`を呼び出す。
5.  `place_native_exit_orders()`は、未計算（`0`）の`self.sl_price`と`self.risk_per_share`を使って決済注文を作成しようとするため、意図したリスク管理が行われない。

**欠陥**: バックテストにおいて、決済パラメータが使用されるタイミングまでに、その計算が完了していない。

-----

### \#\# 3. 修正後（To-Be）のロジックフロー

修正後は、すべての意思決定がシグナルバーの情報に基づいて行われる、一貫したフローを構築する。

1.  `check_entry_conditions`メソッドがシグナルバーでエントリーを決定する。
2.  **【新】** 直ちに同メソッド内で`recalculate_exit_prices()`を呼び出し、シグナルバーのATRに基づいて`self.sl_price`と`self.tp_price`を計算し、インスタンス変数に格納する。
3.  エントリー注文（`buy()`/`sell()`）を発注する。この時点でストラテジーオブジェクトは正確な決済価格を保持している。
4.  次のバーで注文が約定し、`notify_order`メソッドがトリガーされる。
5.  バックテスト用のロジックパスは`place_native_exit_orders()`を呼び出す。
6.  `place_native_exit_orders()`は、**ステップ2で事前に計算・保持しておいた正確なSL/TP価格**を用いて、正しいOCO決済注文を発注する。

-----

### \#\# 4. 実装変更の詳細

**対象ファイル**: `src/core/strategy.py`

#### **4.1. `check_entry_conditions` メソッドの変更**

`place_order`内部関数のロジックを修正し、注文前に決済価格を計算する。

  * **変更前**:

    ```python
    # src/core/strategy.py -> check_entry_conditions -> place_order
    def place_order(trade_type, reason):
        # ...
        if not self.live_trading:
            self.recalculate_exit_prices(entry_price, is_long)

        self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}")
        self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)
        # ...
    ```

  * **変更後**:

    ```python
    # src/core/strategy.py -> check_entry_conditions -> place_order
    def place_order(trade_type, reason):
        self.entry_reason = reason
        is_long = trade_type == 'long'
        
        # 注文前にSL/TP価格を計算するロジックをここに集約
        self.recalculate_exit_prices(entry_price, is_long)

        self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}")
        self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)
        # ...
    ```

  * **変更理由**: `if not self.live_trading:`の分岐をなくし、バックテストとリアルタイム取引の両方で、一貫してエントリー注文前に決済価格を計算する。これにより、ロジックが統一され、堅牢性が向上する。

#### **4.2. `notify_order` メソッドの変更**

リアルタイム取引時の冗長な決済価格計算ロジックを削除する。

  * **変更前**:

    ```python
    # src/core/strategy.py -> notify_order
    if is_entry:
        # ...
        if not self.live_trading:
            self.place_native_exit_orders()
        else:
            is_long = order.isbuy()
            entry_price = order.executed.price
            if self.tp_price == 0.0 and self.sl_price == 0.0:
                 self.recalculate_exit_prices(entry_price, is_long) # <-- この部分が冗長
            self.log(f"ライブモード決済監視開始: ...")
    ```

  * **変更後**:

    ```python
    # src/core/strategy.py -> notify_order
    if is_entry:
        # ...
        if not self.live_trading:
            self.place_native_exit_orders()
        else:
            # is_long = order.isbuy()
            # entry_price = order.executed.price
            # 上記2行も不要であれば削除可能
            self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, SL={self.sl_price:.2f}")
    ```

  * **変更理由**: `check_entry_conditions`で既に決済価格が計算済みのため、約定後に再計算するロジックは不要であり、ロジックの一貫性を損なう原因となるため削除する。

-----

### \#\# 5. 期待される効果

  * バックテストの**先読みバイアスが排除**され、結果の信頼性が大幅に向上する。
  * バックテストとリアルタイム取引におけるリスク計算のロジックが統一され、**システム全体の整合性が高まる。**
  * `bef`コードと同等の、**論理的に正しいバックテスト結果**が得られるようになる。