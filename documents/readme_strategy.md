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

##### **1.1. 条件の基本構造**

各条件（-で始まる行）は、以下のキーで構成されます。

| パラメータ | 必須/任意 | 説明 | 設定例 |
| :---- | :---- | :---- | :---- |
| timeframe | **必須** | 条件を評価する時間足。long, medium, shortのいずれかを指定。 | "long" |
| type | 任意 | 条件の種類をcrossoverまたはcrossunderにしたい場合に指定。 | "crossover" |
| indicator | typeがない場合**必須** | **比較条件**で使用するインジケーターを定義します。 | {...} |
| compare | typeがない場合**必須** | **比較条件**の比較演算子。 | "\>" |
| target | typeがない場合**必須** | **比較条件**の比較対象。 | {...} |
| indicator1 indicator2 | typeがある場合**必須** | **クロス条件**で使用する2つのインジケーター。 | {...} |

##### **1.2. indicator / indicator1 / indicator2 の詳細**

インジケーターを定義するブロックです。

| キー | 必須/任意 | 説明 | 設定例 |
| :---- | :---- | :---- | :---- |
| name | **必須** | インジケーター名。backtrader準拠。 | "ema", "sma", "rsi" |
| params | 任意 | インジケーターのパラメータ。 | { "period": 14 } |

**Note:** backtraderでサポートされているインジケーター（sma, ema, rsi, macd, stochasticなど）がnameとして利用可能です。

##### **1.3. compare の種類**

比較条件で使用する演算子です。

| 値 | 説明 |
| :---- | :---- |
| \> | 左辺（indicator）が右辺（target）より大きい |
| \< | 左辺が右辺より小さい |
| between | 左辺が右辺の範囲内にある |

##### **1.4. target の詳細**

インジケーターの比較対象を定義するブロックです。

| キー | 必須/任意 | 説明 | 設定例 |
| :---- | :---- | :---- | :---- |
| type | **必須** | 比較対象の種別。 | "data" (ローソク足) or "values" (固定値) |
| value | **必須** | typeに応じた具体的な値。 | "close", \[30, 70\] |

compareがbetweenの場合、valueには必ず数値を2つ指定します (例: \[30, 70\])。  
compareが\>や\<の場合、valueには数値を1つ指定します (例: \[70\])。

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