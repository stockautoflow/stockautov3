# **ATRトレーリングストップ 実装仕様書 (v7.2)**

## **1\. 概要**

### **1.1. 目的**

利益を自動で追従（トレール）させながら損失を限定する、よりダイナミックな決済戦略を可能にするため、**ATRトレーリングストップ**機能を実装する。これにより、トレンド相場での利益最大化を目指す。

### **1.2. 実装方針**

ATRトレーリングストップの実装は、以下の2つの主要な改修によって実現されている。

1. **strategy.ymlの拡張**: 決済ロジックの定義にatr\_trailing\_stopタイプを追加し、設定ファイルからトレーリングストップを容易に有効化できるようにした。  
2. **btrader\_strategy.pyの改修**: 従来のbuy\_bracket/sell\_bracket注文を廃止。エントリー、利確、損切りの各注文を個別に管理し、ポジション保有中にローソク足ごとストップロス価格を動的に更新するロジックを実装した。

## **2\. strategy.yml 仕様**

exit\_conditions.stop\_lossセクションのtypeキーで、固定損切りとトレーリングストップ損切りを切り替える。

### **2.1. 設定項目**

| キー | 説明 | 設定例 |
| :---- | :---- | :---- |
| type | **atr\_trailing\_stop** を指定する。(atr\_multipleで固定損切り) | atr\_trailing\_stop |
| timeframe | ATRの計算に使用する時間足を指定します。（short, medium, long） | short |
| params.period | ATRの期間。 | 14 |
| params.multiplier | 価格から離すATRの倍率。 | 2.5 |

### **2.2. 設定例**

\# strategy.yml

\# ... (entry\_conditions, sizing など)

exit\_conditions:  
  \# 利確は固定ATR、もしくはこのセクション自体を削除することも可能  
  take\_profit:  
    type: "atr\_multiple"  
    timeframe: "short"  
    params: { period: 14, multiplier: 5.0 }

  \# 損切りロジックをトレーリングストップに変更  
  stop\_loss:  
    type: "atr\_trailing\_stop"  \#  \<-- トレーリングストップを指定  
    timeframe: "short"         \# ATRを計算する時間足  
    params:  
      period: 14             \# ATRの期間  
      multiplier: 2.5        \# ATRの倍率

## **3\. btrader\_strategy.py 実装仕様**

トレーリングストップを実現するため、注文管理ロジックが根本的に変更された。

### **3.1. 主要な変更点**

* **注文方式の変更**: buy\_bracket/sell\_bracketの使用を停止。代わりに、エントリー注文 (self.entry\_order)、利確注文 (self.limit\_order)、損切り注文 (self.stop\_order) を個別のインスタンス変数で管理する。  
* **next()メソッドのロジック分離**: ポジション保有中と非保有中で処理を分離し、保有中にはストップ価格の更新ロジックを実行する。  
* **notify\_order()での連携**: エントリー注文約定後に、利確・損切り注文を自動で発注する。また、どちらかの決済注文が約定した際に、もう一方を自動でキャンセルする。

### **3.2. 実装詳細**

#### **3.2.1. エントリー処理 (nextメソッド内)**

* ポジションがない場合、strategy.ymlのエントリー条件を評価する。  
* 条件が成立した場合、self.buy()またはself.sell()で**エントリー注文のみを発注**する。  
* この時点ではまだ損切り・利確注文は発注されない。

#### **3.2.2. 決済注文の発注 (notify\_orderメソッド内)**

* エントリー注文 (self.entry\_order) の約定を検知する (order.status \== order.Completed)。  
* 約定後、strategy.ymlのexit\_conditionsに基づき、以下の注文を**直ちに発注**する。  
  1. **利確注文 (オプション)**: take\_profitが定義されていれば、self.sell(exectype=bt.Order.Limit, ...)の形で発注し、self.limit\_orderに保存。  
  2. **初回ストップ注文**: self.sell(exectype=bt.Order.Stop, ...)の形で発注し、self.stop\_orderに保存。

#### **3.2.3. トレーリングストップ処理 (nextメソッド内)**

* if self.position:ブロック内で、ポジション保有中に毎ローソク足で実行される。  
* stop\_loss.typeがatr\_trailing\_stopであり、かつストップ注文(self.stop\_order)が有効な場合に処理を開始する。  
* **ロングポジションの場合**:  
  1. 新しいストップ価格を計算: new\_stop\_price \= self.data.close\[0\] \- (self.atr\[0\] \* multiplier)  
  2. **new\_stop\_priceが現在のストップ価格 (self.stop\_order.created.price) よりも高い場合（＝より有利な場合）にのみ**、更新処理を行う。  
  3. 更新処理:  
     a. 既存のストップ注文をキャンセル: self.broker.cancel(self.stop\_order)  
     b. 新しい価格で再度ストップ注文を発注し、self.stop\_orderを上書きする。  
* **ショートポジションの場合**:  
  1. 新しいストップ価格を計算: new\_stop\_price \= self.data.close\[0\] \+ (self.atr\[0\] \* multiplier)  
  2. **new\_stop\_priceが現在のストップ価格よりも低い場合にのみ**、同様に更新処理を行う。

#### **3.2.4. 決済完了処理 (notify\_orderメソッド内)**

* 利確注文 (self.limit\_order) または損切り注文 (self.stop\_order) のどちらかの約定を検知する。  
* 約定後、トレードはクローズされる。  
* **もう一方の有効な注文を明示的にキャンセル**する処理を実行する。  
  * 例：損切り注文が約定した場合、if self.limit\_order and self.limit\_order.alive(): self.broker.cancel(self.limit\_order) を実行。

## **4\. 期待される動作**

この実装により、以下のトレード動作が実現される。

1. strategy.ymlの条件に基づきエントリー注文が約定する。  
2. 約定と同時に、ATRに基づいた初期ストップロス価格と、利確価格（設定されていれば）で注文が設定される。  
3. 価格が利益の出る方向に動くと、ストップロス価格が価格に追従して自動的に切り上がる（または切り下がる）。価格が逆行しても、一度上がったストップロス価格は下がらない。  
4. 最終的に、価格が更新されたストップロスラインに達するか、または利確ラインに達すると、ポジションが決済される。