# **トレード戦略のカスタマイズ方法 (v7.2)**

このシステムでは、トレードのロジックはすべてstrategy.ymlファイルで定義します。このファイルを編集することで、プログラミングの知識がなくても様々な戦略を試すことができます。

### **1\. エントリー条件の定義 (entry\_conditions)**

エントリー条件は、long（買い）とshort（売り）のそれぞれについて、満たすべき条件をリスト形式で記述します。リスト内の条件はすべて満たされる必要があります（AND条件）。

**設定例:**

entry\_conditions:  
  long: \# ロングエントリー条件  
    \# 条件1: 長期足でEMA(20)より価格が上  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 20 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \# 条件2: 短期足でEMA(2)がEMA(5)をゴールデンクロス  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 2 } }, indicator2: { name: "ema", params: { period: 5 } } }

#### **主要パラメータ解説**

* timeframe: 条件を評価する時間足 (long, medium, short)。  
* type: crossover（ゴールデンクロス）または crossunder（デッドクロス）を指定。  
* indicator, indicator1, indicator2: name (例: ema, rsi) と params (例: { period: 14 }) でインジケーターを指定。  
* compare: 比較演算子 (\>, \<, between)。  
* target: 比較対象。type (data or values) と value (例: close, \[30, 70\]) で指定。

### **2\. イグジット条件の定義 (exit\_conditions)**

ATR（アベレージ・トゥルー・レンジ）に基づいた利確と損切りのルールを定義します。

**設定例:**

exit\_conditions:  
  \# 利確ルール (ATRの5倍で固定利確)  
  take\_profit:  
    type: "atr\_multiple"  
    timeframe: "short"  
    params: { period: 14, multiplier: 5.0 }

  \# 損切りルール (ATRの2.5倍でトレーリングストップ)  
  stop\_loss:  
    type: "atr\_trailing\_stop"  
    timeframe: "short"  
    params:  
      period: 14  
      multiplier: 2.5

#### **主要パラメータ解説**

* take\_profit: 利確ルールを定義します。  
* stop\_loss: 損切りルールを定義します。  
* type:  
  * atr\_multiple: エントリー時のATRに基づいて**固定の**利確/損切り価格を決定します。  
  * atr\_trailing\_stop: **（stop\_loss専用）** 利益方向に価格が動くと、損切りラインが自動で追従（トレール）します。  
* timeframe: ATR計算に使用する時間足。  
* params: period（ATR期間）と multiplier（ATR倍率）を指定します。

### **3\. ポジションサイジングの定義 (sizing)**

1トレードあたりのリスクに基づいて、ポジションサイズを自動計算します。

**設定例:**

sizing:  
  \# 1トレードあたり、総資金の1%をリスクに晒す  
  risk\_per\_trade: 0.01

#### **仕組み**

ポジションサイズは、以下の計算式で決定されます。

1. 1株あたりのリスク額を計算:  
   risk\_per\_share \= ATR \* stop\_lossのmultiplier  
2. ポジションサイズを決定:  
   size \= (現在の総資金 \* risk\_per\_trade) / risk\_per\_share

これにより、ボラティリティが高い相場ではポジションサイズが小さく、低い相場では大きくなるように自動で調整されます。

### **カスタマイズの手順**

1. strategy.yml ファイルをテキストエディタで開きます。  
2. entry\_conditions, exit\_conditions, sizing セクションに、試したい戦略のロジックを記述します。  
3. ファイルを保存します。  
4. ターミナルで python run\_backtrader.py を実行し、変更した戦略でバックテストを行います。  
5. python app.py を実行し、ブラウザで分析結果を確認します。

このプロセスを繰り返すことで、コードを一切触らずに、様々な**エントリー・イグジット・資金管理戦略**の有効性を高速に検証することが可能です。