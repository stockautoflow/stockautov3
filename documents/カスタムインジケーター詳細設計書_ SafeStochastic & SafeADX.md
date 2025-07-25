# **カスタムインジケーター詳細設計書: SafeStochastic & SafeADX**

## **1\. 概要**

本ドキュメントは、株価自動トレードシステムで使用されるカスタムインジケーター SafeStochastic および SafeADX の詳細設計について記述する。これらのインジケーターは、標準ライブラリ（Backtrader）の計算ロジックを継承しつつ、特定の市場状況下で発生しうるゼロ除算エラーを回避し、システムの安定性を向上させることを目的として特別に設計されている。

## **2\. SafeStochastic 詳細設計**

### **2.1. 目的**

標準のストキャスティクス・オシレーター計算において、特定の条件下で発生するゼロ除算エラーを未然に防ぎ、システムのクラッシュを回避する。

### **2.2. ゼロ除算が発生するシナリオ**

ストキャスティクスの主要な計算式 %K は以下のように定義される。

%K \= (現在の終値 \- 過去N日間の最安値) / (過去N日間の最高値 \- 過去N日間の最安値)

この計算式の分母である (過去N日間の最高値 \- 過去N日間の最安値) がゼロになる、すなわち**最高値と最安値が同値**になった場合にゼロ除算が発生する。これは、市場が全く動いていない（例：ストップ高/安、取引停止、ティックデータでの同値連続）場合に起こりうる。

### **2.3. 回避ロジック**

src/core/indicators.py に実装されている SafeStochastic は、next() メソッド（ローソク足データが更新されるたびに呼び出される）の冒頭で、ゼロ除算の条件を事前にチェックする。

1. 条件判定:  
   現在のローソク足における最高値 (self.data.high\[0\]) と最安値 (self.data.low\[0\]) の差がゼロであるかを確認する。  
   if self.data.high\[0\] \- self.data.low\[0\] \== 0:

2. フォールバック処理:  
   条件が真（最高値と最安値が同値）の場合、ゼロ除算となる計算をスキップし、%K および %D の値として、相場に方向性がないことを示す中立的な値である 50.0 を強制的に代入する。  
   self.lines.percK\[0\] \= 50.0  
   self.lines.percD\[0\] \= 50.0

3. 通常処理:  
   条件が偽の場合、ゼロ除算の危険はないため、親クラスである bt.indicators.Stochastic の標準的な計算処理 (super().next()) を実行する。

### **2.4. 期待される効果**

この設計により、値動きのない状況でもシステムがクラッシュすることなく安定して稼働を続ける。また、中立値である50.0を返すことで、その後の取引戦略に極端な影響を与えることなく、安全に処理を継続できる。

## **3\. SafeADX 詳細設計**

### **3.1. 目的**

ADX (Average Directional Movement Index) の複雑な計算過程に存在する2つのゼロ除算リスクを排除し、いかなる市場状況でも安定して値を算出できる、自己完結型の堅牢なインジケーターを実装する。

### **3.2. ゼロ除算が発生するシナリオ**

ADXの計算過程では、以下の2段階でゼロ除算が発生する可能性がある。

#### **シナリオ1: DI (Directional Indicator) 計算時**

\+DI と \-DI は、以下の計算式で求められる。

\+DI \= 100 \* (+DMの移動平均) / TRの移動平均  
\-DI \= 100 \* (-DMの移動平均) / TRの移動平均

ここで分母となる **TR (True Range) の移動平均がゼロ**になった場合（値動きが全くない状態が続いた場合）にゼロ除算が発生する。

#### **シナリオ2: DX (Directional Movement Index) 計算時**

ADXの元となる DX は、以下の計算式で求められる。

DX \= 100 \* |+DI \- \-DI| / (+DI \+ \-DI)

ここで分母となる **(+DI \+ \-DI) の合計値がゼロ**になった場合にゼロ除算が発生する。これは、トレンドが全く発生していない状況で起こりうる。

### **3.3. 回避ロジック**

src/core/indicators.py に実装されている SafeADX は、各計算ステップで分母がゼロになる可能性をチェックし、安全な値にフォールバックする。

1. DI計算時の回避ロジック:  
   TR の移動平均値である self.tr がゼロに極めて近いかどうかを、浮動小数点数の誤差を考慮して 1e-9 (0.000000001) と比較する。  
   if self.tr \> 1e-9:  
       self.plus\_di \= 100.0 \* self.plus\_dm / self.tr  
       self.minus\_di \= 100.0 \* self.minus\_dm / self.tr  
   else:  
       self.plus\_di \= 0.0  
       self.minus\_di \= 0.0  
   \`\`\`self.tr\` がほぼゼロの場合、計算をスキップし、\`+DI\` と \`-DI\` に \`0.0\` を代入する。

2. DX計算時の回避ロジック:  
   同様に、+DI と \-DI の合計値 di\_sum がゼロに極めて近いかどうかを 1e-9 と比較する。  
   di\_sum \= self.plus\_di \+ self.minus\_di  
   dx \= 0.0  
   if di\_sum \> 1e-9:  
       dx \= 100.0 \* abs(self.plus\_di \- self.minus\_di) / di\_sum  
   \`\`\`di\_sum\` がほぼゼロの場合、計算をスキップし、\`DX\` には初期値である \`0.0\` が使用される。

### **3.4. 期待される効果**

この2段階のチェック機構により、値動きが極端に小さい、または全くない相場においても、ADX関連の計算がゼロ除算で失敗することがなくなる。これにより、システムのいかなる状況下での安定稼働にも大きく貢献する。