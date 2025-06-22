# **ATRトレーリングストップ 実装仕様書 (v73.7)**

## **1\. 概要**

### **1.1. 目的**

利益を自動で追従（トレール）させながら損失を限定する、よりダイナミックな決済戦略を可能にするため、**ATRトレーリングストップ**機能を実装する。これにより、トレンド相場での利益最大化を目指す。

### **1.2. 実装方針**

ATRトレーリングストップは、Backtraderの**ネイティブ機能**であるbt.Order.StopTrailとOCO（One-Cancels-Other）注文を活用して実現されている。これにより、手動での価格追従ロジックを排除し、信頼性とシンプルさを向上させた。

1. **strategy.ymlの拡張**: exit\_conditions.stop\_lossセクションのtypeキーでatr\_stoptrailを指定できるようにした。  
2. **btrader\_strategy.pyの改修**: エントリー注文の約定後(notify\_order)に、利確注文（Limit）とトレーリングストップ注文（StopTrail）を**OCO注文として一度だけ発注**するロジックに変更した。

## **2\. strategy.yml 仕様**

exit\_conditions.stop\_lossセクションで設定する。

### **2.1. 設定項目**

| キー | 説明 | 設定例 |  
| type | atr\_stoptrail を指定する。(atr\_multipleで固定損切り) | atr\_stoptrail |  
| timeframe | ATRの計算に使用する時間足を指定します。（short, medium, long） | short |  
| params.period | ATRの期間。 | 14 |  
| params.multiplier | ATRの倍率。trailamount（トレール幅）として使用される。 | 2.5 |

### **2.2. 設定例**

\# strategy.yml

exit\_conditions:  
  \# 利確は固定ATR、もしくはこのセクション自体を削除することも可能  
  take\_profit:  
    type: "atr\_multiple"  
    timeframe: "short"  
    params: { period: 14, multiplier: 5.0 }

  \# 損切りロジックをトレーリングストップに変更  
  stop\_loss:  
    type: "atr\_stoptrail"         \# \<-- ネイティブトレーリングストップを指定  
    timeframe: "short"            \# ATRを計算する時間足  
    params:  
      period: 14                \# ATRの期間  
      multiplier: 2.5           \# ATRの倍率

## **3\. btrader\_strategy.py 実装仕様**

### **3.1. 主要な変更点**

* **注文方式の変更**: next()メソッドでの手動トレーリングロジックを完全に廃止。  
* **ネイティブOCO注文**: notify\_order()内で、エントリー約定後に利確注文とStopTrail注文をOCOで連携させる方式に変更。

### **3.2. 実装詳細**

#### **3.2.1. エントリー処理 (nextメソッド内)**

* ポジションがない場合、strategy.ymlのエントリー条件を評価する。  
* 条件が成立した場合、self.buy()またはself.sell()で**成行のエントリー注文のみを発注**する。  
* この時点ではまだ決済注文は発注されない。

#### **3.2.2. 決済注文の発注 (notify\_orderメソッド内)**

* エントリー注文 (self.entry\_order) の約定を検知する (order.status \== order.Completed)。  
* 約定後、\_place\_exit\_orders()メソッドが呼び出され、以下の注文が**直ちに発注**される。  
  1. **利確注文 (オプション)**: take\_profitが定義されていれば、exectype=bt.Order.Limitの注文が\*\*送信保留 (transmit=False)\*\*で作成される。  
  2. **トレーリングストップ注文**: exectype=bt.Order.StopTrailの注文が発注される。この際、oco引数に上記1の利確注文を渡すことで、2つの注文が自動的に連携される。  
* これにより、どちらか一方が約定すれば、もう一方は自動的にBacktraderによってキャンセルされる。

#### **3.2.3. トレーリングストップ処理**

* **完全にBacktraderエンジンに委任**される。  
* next()メソッド内でポジション保有中にストップ価格を監視・更新する手動ロジックは**存在しない**。これにより、「幽霊トレード」などの潜在的なバグを根本的に排除している。

## **4\. 期待される動作**

この実装により、以下のトレード動作が実現される。

1. strategy.ymlの条件に基づきエントリー注文が約定する。  
2. 約定と同時に、Backtraderが**利確注文とトレーリングストップ注文をOCOで管理開始**する。  
3. 価格が利益の出る方向に動くと、BacktraderのStopTrailロジックに従い、ストップロス価格が自動的に切り上がる（または切り下がる）。  
4. 最終的に、価格が更新されたストップロスラインに達するか、または利確ラインに達すると、ポジションが決済され、OCO連携されたもう一方の注文は自動でキャンセルされる。