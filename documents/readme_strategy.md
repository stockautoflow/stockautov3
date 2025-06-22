### **トレード戦略のカスタマイズ方法 (v73.7)**

このシステムでは、トレードのロジックはすべてstrategy.ymlファイルで定義します。このファイルを編集することで、プログラミングの知識がなくても様々な戦略を試すことができます。

### **1\. エントリー条件の定義 (entry\_conditions)**

エントリー条件は、long（買い）とshort（売り）のそれぞれについて、満たすべき条件をリスト形式で記述します。リスト内の条件はすべて満たされる必要（AND条件）があります。

**設定例:**

entry\_conditions:  
  long: \# ロングエントリー条件  
    \# 条件1: 長期足で20EMAより上  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 20 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \# 条件2: 短期足でゴールデンクロス  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

#### **主要パラメータ解説**

* **timeframe**: (必須) 条件を評価する時間足 (long, medium, short)。  
* **type**: (任意) crossoverまたはcrossunderを指定。  
* **indicator / indicator1 / indicator2**:  
  * name: (必須) backtrader準拠のインジケーター名 ("ema", "rsi"など)。  
  * params: (任意) インジケーターのパラメータ。  
* **compare**: (typeがない場合必須) 比較演算子 ("\>", "\<", "between"\`)。  
* **target**: (typeがない場合必須\`) 比較対象。  
  * type: (必須) "data" (ローソク足) または "values" (固定値)。  
  * value: (必須) typeに応じた具体的な値。compareがbetweenの場合は数値を2つ指定 (\[30, 70\])。

### **2\. イグジット条件の定義 (exit\_conditions)**

ATR（Average True Range）に基づいた損切りと利確のルールを定義します。**このセクションは現在、完全に機能します。**

**設定例:**

exit\_conditions:  
  \# 利確ルール (任意)  
  take\_profit:  
    type: "atr\_multiple"  
    timeframe: "short"  
    params: { period: 14, multiplier: 5.0 }

  \# 損切りルール (必須)  
  stop\_loss:  
    type: "atr\_stoptrail"  \# Backtraderネイティブのトレーリングストップ  
    timeframe: "short"  
    params:  
      period: 14  
      multiplier: 2.5

#### **主要パラメータ解説**

* **type**:  
  * "atr\_multiple": エントリー時のATRに基づいて、固定の損益幅を設定します。  
  * "atr\_stoptrail": エントリー時のATRに基づいて初期ストップロスを設定し、その後は価格に追従（トレール）します。  
* **timeframe**: ATR計算に使用する時間足。  
* **params**:  
  * period: ATRの計算期間。  
  * multiplier: ATRの値を何倍するかを指定。

### **3\. ポジションサイジングの定義 (sizing)**

1トレードあたりのリスクに基づいて、ポジションサイズ（取引数量）を自動で計算します。**このセクションは現在、完全に機能します。**

**設定例:**

sizing:  
  \# 1トレードあたりのリスクを総資金の1%に設定  
  risk\_per\_trade: 0.01  
  \# 1トレードあたりの最大投資額を1000万円に制限  
  max\_investment\_per\_trade: 10000000

### **カスタマイズの手順**

1. strategy.yml ファイルをテキストエディタで開きます。  
2. entry\_conditions, exit\_conditions, sizing セクションに、試したいルールを記述します。  
3. ファイルを保存します。  
4. ターミナルで python run\_backtrader.py を実行し、変更した戦略でバックテストを行います。  
5. python app.py を実行し、ブラウザで分析結果を確認します。

このプロセスを繰り返すことで、コードを一切触らずに、様々な戦略の有効性を高速に検証することが可能です。