はい、承知いたしました。  
これまでの議論で確定した最終仕様に基づき、リファクタリングの設計書をMarkdown形式で作成します。

---

# **DynamicStrategy リファクタリング設計書**

## **1\. 概要**

### **1.1. 背景と目的**

現行のsrc/core/strategy.pyに実装されているDynamicStrategyクラスは、初期化、取引判断、注文、状態管理など多数の責務を担っており、コードの複雑性が増大している。

本設計は、**単一責任の原則**に基づきクラスを分割し、各コンポーネントの独立性を高めることで、**保守性・可読性・テスト容易性**を向上させることを目的とする。

### **1.2. 設計方針**

* **オーケストレーターと専門家モデル**: DynamicStrategyを各専門コンポーネントを**統括・指揮する**「オーケストレーター」と位置づけ、具体的な処理は専門家クラスに委譲する。  
* **コンポジション（合成）**: 継承ではなく、オーケストレーターが専門家クラスのインスタンスを保持（合成）する構成を採用する。

---

## **2\. アーキテクチャ**

### **2.1. コンポーネント構成**

src/core/strategy/ディレクトリ配下に、以下の9つのコンポーネント（クラス）を配置する。

| ファイル名 | クラス名 | 役割 |
| :---- | :---- | :---- |
| strategy\_orchestrator.py | DynamicStrategy | 🎼 **司令塔 (オーケストレーター)** |
| strategy\_initializer.py | StrategyInitializer | ⚙️ **初期化と設定** |
| entry\_signal\_generator.py | EntrySignalGenerator | 🧠 **エントリーシグナル生成** |
| exit\_signal\_generator.py | ExitSignalGenerator | 🔐 **エグジットシグナル生成** |
| order\_manager.py | OrderManager | 🚀 **注文の発注** |
| position\_manager.py | PositionManager | 💾 **ポジションの状態管理と復元** |
| event\_handler.py | EventHandler | 📋 **イベントの解釈・情報整形** |
| strategy\_logger.py | StrategyLogger | ✍️ **情報のログ記録** |
| strategy\_notifier.py | StrategyNotifier | 📧 **情報のメール通知** |

### **2.2. 連携シーケンス**

コンポーネント間の主要な連携フローは以下の通りである。

#### **エントリーシーケンス**

\!([https://i.imgur.com/example.png](https://www.google.com/search?q=https://i.imgur.com/example.png&authuser=5))

1. **DynamicStrategy**: next()でポジションがないことを確認。  
2. → **EntrySignalGenerator**: check\_entry\_signal()を呼び出し、エントリーシグナルを要求。  
3. ← **EntrySignalGenerator**: シグナル（例: 'long'）とエントリー根拠を返す。  
4. → **OrderManager**: place\_entry\_order()を呼び出し、シグナルに基づき注文を発注。  
5. → **EventHandler**: 注文発注イベントをon\_entry\_order\_placed()で受け取る。  
6. → **StrategyLogger / StrategyNotifier**: 整形された情報をログ記録・通知する。

#### **イベント通知シーケンス (注文約定時)**

1. **backtrader**: 注文状態の更新をDynamicStrategy.notify\_order()に通知。  
2. → **DynamicStrategy**: orderオブジェクトをEventHandler.on\_order\_update()に渡す。  
3. → **EventHandler**: orderの状態（約定、エラー等）を解釈し、メッセージを整形。  
4. → **StrategyLogger / StrategyNotifier**: 整形された情報をログ記録・通知する。

---

## **3\. コンポーネント詳細設計**

### **3.1. strategy\_orchestrator.py (司令塔)**

* **クラス名**: DynamicStrategy  
* **責務**: backtraderのライフサイクル（\_\_init\_\_, next, notify\_order等）をフックし、各専門コンポーネントに処理を適切に委譲する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self): 全コンポーネントをインスタンス化し、依存関係を注入する。  
  * next(self): データ更新時に、ポジションの有無に応じてEntrySignalGeneratorまたはExitSignalGeneratorを呼び出す。  
  * notify\_order(self, order): 注文イベントをEventHandlerに委譲する。  
  * notify\_trade(self, trade): トレードイベントをPositionManagerに委譲する。

### **3.2. strategy\_initializer.py (初期化)**

* **クラス名**: StrategyInitializer  
* **責務**: 戦略パラメータに基づき、取引に必要なインジケーター群を生成する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, strategy\_params)  
  * create\_indicators(self, data\_feeds) \-\> dict: backtraderのインジケーターオブジェクトの辞書を返す。

### **3.3. entry\_signal\_generator.py (エントリーシグナル)**

* **クラス名**: EntrySignalGenerator  
* **責務**: 現在の市場データから、エントリー条件を満たしているかを判断する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, indicators, data\_feeds)  
  * check\_entry\_signal(self, strategy\_params) \-\> (str | None, str | None): シグナル（'long', 'short'）とエントリー根拠（文字列）のタプル、または(None, None)を返す。

### **3.4. exit\_signal\_generator.py (エグジットシグナル)**

* **クラス名**: ExitSignalGenerator  
* **責務**: 保有ポジションの決済条件（利確、損切り）を監視・判断する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, strategy, indicators, order\_manager)  
  * calculate\_and\_set\_exit\_prices(self, entry\_price, is\_long): 決済価格を計算し、内部状態として保持する。  
  * check\_exit\_conditions(self): 決済条件を評価し、条件を満たせばOrderManagerに決済を依頼する。

### **3.5. order\_manager.py (注文発注)**

* **クラス名**: OrderManager  
* **責務**: 注文サイズを算出し、backtraderのAPIを呼び出して実際に注文を発注する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, strategy, sizing\_params, event\_handler)  
  * place\_entry\_order(self, trade\_type, reason, indicators): 新規注文を発注する。  
  * close\_position(self): ポジションを決済する注文を発注する。

### **3.6. position\_manager.py (状態管理)**

* **クラス名**: PositionManager  
* **責務**: ポジションの状態（サイズ、価格等）を保持し、システム再起動時にその状態を復元する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, persisted\_position)  
  * restore\_state(self, strategy, exit\_signal\_generator): strategyオブジェクトの状態を復元する。  
  * on\_trade\_update(self, trade, strategy): トレード開始・終了時にポジション情報を更新する。

### **3.7. event\_handler.py (イベント解釈)**

* **クラス名**: EventHandler  
* **責務**: backtraderからのイベントを人間が読めるメッセージに解釈・整形する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, strategy, logger, notifier)  
  * on\_order\_update(self, order): 注文イベントを解釈し、StrategyLoggerとStrategyNotifierに処理を依頼する。

### **3.8. strategy\_logger.py (ログ記録)**

* **クラス名**: StrategyLogger  
* **責務**: 整形済みのメッセージをログファイルに記録する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, strategy)  
  * log(self, txt, level): 指定されたメッセージをログに出力する。

### **3.9. strategy\_notifier.py (通知)**

* **クラス名**: StrategyNotifier  
* **責務**: 整形済みのメッセージをメール等の手段で外部に通知する。  
* **主要インターフェース**:  
  * \_\_init\_\_(self, live\_trading, strategy)  
  * send(self, subject, body, immediate): 外部通知システムにメッセージ送信を依頼する。