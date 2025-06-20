# **ATRトレーリングストップ 実装仕様提案書**

## **1\. 概要**

### **1.1. 目的**

現在のシステムは、エントリー時に固定の損切り(Stop Loss)と利確(Take Profit)を設定するbuy\_bracket/sell\_bracket注文を使用しています。ここに**ATRトレーリングストップ**機能を追加し、利益を伸ばしつつ損失を限定する、よりダイナミックな決済戦略を可能にすることを目的とします。

### **1.2. 改修方針**

ATRトレーリングストップの実装は、以下の2つの主要な改修によって実現します。

1. **strategy.ymlの拡張**: 決済ロジックの定義にatr\_trailing\_stopタイプを追加し、設定ファイルからトレーリングストップを有効化できるようにします。  
2. **btrader\_strategy.pyの改修**: ポジションを保有している間、ローソク足ごとにストップロス価格を動的に更新するロジックを実装します。

## **2\. strategy.yml 仕様変更**

exit\_conditions.stop\_lossセクションに、新しいtypeとしてatr\_trailing\_stopを追加します。これにより、固定損切りとトレーリングストップ損切りをYAMLファイル上で切り替え可能になります。

### **2.1. 設定項目**

| キー | 説明 | 設定例 |
| :---- | :---- | :---- |
| type | **atr\_trailing\_stop** を指定します。 | atr\_trailing\_stop |
| timeframe | ATRの計算に使用する時間足を指定します。（short, medium, long） | short |
| params.period | ATRの期間。 | 14 |
| params.multiplier | 価格から離すATRの倍率。 | 2.0 |

### **2.2. 設定例**

\# strategy.yml

\# ... (entry\_conditions, sizing などは既存のまま)

exit\_conditions:  
  \# 利確は固定のままでも、削除してトレーリングストップに任せることも可能  
  take\_profit:  
    type: "atr\_multiple"  
    timeframe: "short"  
    params: { period: 14, multiplier: 5.0 }

  \# 損切りロジックをトレーリングストップに変更  
  stop\_loss:  
    type: "atr\_trailing\_stop"  \#  \<-- ここのタイプを変更  
    timeframe: "short"         \# ATRを計算する時間足  
    params:  
      period: 14             \# ATRの期間  
      multiplier: 2.0        \# ATRの倍率

## **3\. btrader\_strategy.py 改修仕様**

トレーリングストップを実現するため、btrader\_strategy.pyの注文管理ロジックを大幅に改修します。

### **3.1. 主要な変更点**

* **注文方式の変更**: buy\_bracket/sell\_bracketの使用を停止します。代わりに、エントリー注文、利確注文、損切り注文を個別に発注・管理します。  
* **状態管理変数の追加**: トレード中の注文状態を管理するため、インスタンス変数（例: self.stop\_order, self.limit\_order）を追加します。  
* **next()メソッドのロジック追加**: ポジション保有中に、毎ローソク足でストップ価格を更新するロジックを追加します。

### **3.2. 実装詳細**

#### **3.2.1. エントリー処理 (nextメソッド内)**

* stop\_loss.typeがatr\_trailing\_stopの場合、buy\_bracketやsell\_bracketは使用しません。  
* 以下の順で注文を発注します。  
  1. **エントリー注文**: 通常のself.buy()またはself.sell()を実行します。  
  2. **利確注文 (オプション)**: take\_profitが定義されていれば、self.sell(exectype=bt.Order.Limit, price=tp\_price)の形で発注します。  
  3. **初回ストップ注文**: self.sell(exectype=bt.Order.Stop, price=sl\_price)の形で発注します。  
* 発注した利確注文と損切り注文のオブジェクトは、self.limit\_orderやself.stop\_orderといったインスタンス変数に保存し、後でキャンセルや更新ができるようにします。

#### **3.2.2. トレーリングストップ処理 (nextメソッド内)**

* if self.position:ブロックを追加し、ポジション保有中の処理を記述します。  
* **ロングポジションの場合**:  
  1. 新しいストップ価格を計算します: new\_stop\_price \= self.data.close\[0\] \- (self.atr\[0\] \* multiplier)  
  2. 現在のストップ価格 (self.stop\_order.created.price) よりも新しいストップ価格が高い場合（＝より有利な場合）にのみ、更新処理を行います。  
  3. 更新処理:  
     a. 既存のストップ注文をキャンセルします: self.broker.cancel(self.stop\_order)  
     b. 新しい価格で再度ストップ注文を発注し、self.stop\_orderを更新します。  
* **ショートポジションの場合**:  
  1. 新しいストップ価格を計算します: new\_stop\_price \= self.data.close\[0\] \+ (self.atr\[0\] \* multiplier)  
  2. 現在のストップ価格よりも新しいストップ価格が低い場合にのみ、同様に更新処理を行います。

#### **3.2.3. 決済処理 (notify\_order / notify\_tradeメソッド内)**

* 利確注文または損切り注文のどちらかが約定（order.status \== order.Completed）したら、トレードはクローズされます。  
* トレードがクローズしたことを検知したら（notify\_tradeのif trade.isclosed:）、まだ有効な状態のもう一方の注文（利確注文 or 損切り注文）を明示的にキャンセルする処理が必要です。  
  * 例：損切り注文が約定した場合、self.broker.cancel(self.limit\_order)を実行する。

## **4\. リスクと注意点**

* 注文管理の複雑化:  
  buy\_bracketによる自動的なOCO(One-Cancels-Other)機能が使えなくなるため、notify\_orderとnotify\_tradeでの決済後注文キャンセル処理を正確に実装する必要があります。  
* バックテストの実行速度:  
  毎ローソク足で価格と注文の評価を行うため、バックテストの実行速度がわずかに低下する可能性があります。

## **5\. 期待される動作**

この改修により、以下のようなトレード動作が実現されます。

1. strategy.ymlの条件に基づきエントリー。  
2. エントリーと同時に、ATRに基づいた初期ストップロス価格と、固定の利確価格が設定される。  
3. 価格が利益の出る方向に動くと、ストップロス価格が価格に追従して自動的に切り上がる（または切り下がる）。  
4. 価格が逆行し、更新されたストップロスラインに達するか、または利確ラインに達すると、ポジションが決済される。