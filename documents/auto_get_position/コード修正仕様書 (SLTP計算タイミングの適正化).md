はい、承知いたしました。
最新のコード（`aft`版と同等のもの）を拝見しました。これをベースに、「エントリーを決定したシグナルバーのATR値で計算する方法」へと修正するための仕様書を作成します。

-----

### **`aft`コード修正仕様書 (SL/TP計算タイミングの適正化)**

#### **1. 修正の目的**

現在のコードにおけるバックテストの決済ロジックを、\*\*先読みバイアス（Look-ahead Bias）\*\*を排除した信頼性の高いものに修正する。

具体的には、損切り（SL）・利確（TP）価格の計算タイミングを、エントリー注文が**約定したバー**から、エントリー条件が成立した**シグナルバー**へと変更する。これにより、バックテストの再現性と論理的整合性を確保し、より信頼性の高い戦略評価を可能にする。

-----

#### **2. 現状の仕様の問題点**

現在のバックテストロジックでは、SL/TP価格がエントリー約定後に計算されるか、あるいは全く計算されないフロー上の欠陥がある。

1.  `check_entry_conditions`メソッドがエントリーを決定し、注文を発注する。**この時点では、SL/TP価格は計算されていない (`0`のまま)。**
2.  注文が約定し、`notify_order`メソッドが呼び出される。
3.  `notify_order`内のバックテスト用ロジックは`place_native_exit_orders()`を呼び出すが、このメソッドは**計算済みの`self.tp_price`等を使うことを前提**としており、結果的に不正確な価格（`0`）で決済注文が出されてしまう。

このフローでは、シグナルバーのATRではなく、1本以上未来のバーの情報でSL/TPが決まる（あるいは決まらない）ことになり、バックテストの信頼性を著しく損なう。

-----

#### **3. 修正後の仕様（あるべき姿）**

SL/TP価格の計算をエントリー注文の発注直前に行うことで、全ての意思決定をシグナルバーの情報に統一する。

1.  `next`メソッドがエントリー条件成立を検知する。
2.  `check_entry_conditions`内で、シグナルバーのATR値を取得する。
3.  そのATR値を使い、**SL価格とTP価格を計算して`self.sl_price`等のインスタンス変数に格納する。**
4.  **計算完了直後に**、エントリー注文（`buy`/`sell`）を発注する。
5.  エントリー注文が約定し、`notify_order`が呼び出される。
6.  `notify_order`は、**ステップ3で事前に計算・保存しておいたSL/TP価格を使い**、決済用のOCO注文を発注する。

-----

#### **4. 具体的な修正箇所**

修正は`src/core/strategy.py`内の`DynamicStrategy`クラスに集中する。

**A. `check_entry_conditions`メソッドの修正**
このメソッド内にある`place_order`関数が主な修正対象となる。

  * **修正内容**:
    エントリー注文 (`self.buy()` / `self.sell()`) を呼び出す**前**に、`self.recalculate_exit_prices(entry_price, is_long)`を呼び出すコードを追加する。

  * **修正後のコードイメージ**:

    ```python
    # src/core/strategy.py -> check_entry_conditions -> place_order
    def place_order(trade_type, reason):
        self.entry_reason = reason
        is_long = trade_type == 'long'
        
        # ▼▼▼ この一行を'if not self.live_trading:'ブロックから移動・修正する ▼▼▼
        # エントリー注文を出す前に、シグナルバーの情報でSL/TPを計算・保存する
        self.recalculate_exit_prices(entry_price, is_long)

        self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}")
        self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)

        # ...（通知処理はそのまま）
    ```

    *現在のコードにある `if not self.live_trading:` の条件分岐を削除し、常に `recalculate_exit_prices` が呼ばれるようにする。*

**B. `notify_order`メソッドの修正**
リアルタイム取引とバックテストのロジックを統一するため、`live_trading`時の冗長な再計算処理を削除する。

  * **修正内容**:
    `is_entry`が`True`の場合の`else`節（`live_trading`が`True`の場合の処理）から、`self.recalculate_exit_prices(...)`の呼び出しを含む`if`ブロックを**削除**する。

  * **修正後のコードイメージ**:

    ```python
    # src/core/strategy.py -> notify_order
    if is_entry:
        # ...（subject, bodyの定義）
        self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
        
        if not self.live_trading:
            self.place_native_exit_orders()
        else:
            is_long = order.isbuy()
            entry_price = order.executed.price
            
            # ▼▼▼ このif文ブロックを削除する ▼▼▼
            # if self.tp_price == 0.0 and self.sl_price == 0.0:
            #      self.recalculate_exit_prices(entry_price, is_long)
            
            self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, SL={self.sl_price:.2f}")

        self.send_notification(subject, body, immediate=True)
    ```

-----

以上の仕様で修正を行うことで、バックテストはシグナルバーの情報のみに基づいて実行されるようになり、信頼性と一貫性が担保される。