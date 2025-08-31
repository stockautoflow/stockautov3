はい、大変失礼いたしました。リファクタリングの議論が先行し、最終的な仕様書を明確なドキュメントとして提示できておりませんでした。

以下に、これまでの議論で確定した最終仕様に基づき、リファクタリング仕様書をMarkdown形式で作成します。

---

# **DynamicStrategy リファクタリング仕様書**

## **1\. 目的 🎯**

単一ファイル (src/core/strategy.py) に集中している責務を機能ごとに分割し、各コンポーネントの独立性を高める。これにより、コードの可読性、メンテナンス性、テスト容易性を向上させることを目的とする。

---

## **2\. リファクタリング方針 📜**

* **単一責任の原則**: 各クラスは、単一の明確な責務のみを持つ。  
* **コンポジション（合成）**: DynamicStrategyクラス（オーケストレーター）が、各機能を担当する専門クラスのインスタンスを保持し、処理を委譲する構成とする。

---

## **3\. 新ファイル構成と役割概要 📁**

src/core/strategy/ ディレクトリを新設し、以下の9つのファイルに分割する。

| ファイル名 | クラス名 | 役割 |
| :---- | :---- | :---- |
| **strategy\_orchestrator.py** | DynamicStrategy | 🎼 **司令塔 (オーケストレーター)** |
| **strategy\_initializer.py** | StrategyInitializer | ⚙️ **初期化と設定** |
| **entry\_signal\_generator.py** | EntrySignalGenerator | 🧠 **エントリーシグナル生成** |
| **exit\_signal\_generator.py** | ExitSignalGenerator | 🔐 **エグジットシグナル生成** |
| **order\_manager.py** | OrderManager | 🚀 **注文の発注** |
| **position\_manager.py** | PositionManager | 💾 **ポジションの状態管理と復元** |
| **event\_handler.py** | EventHandler | 📋 **イベントの解釈・情報整形** |
| **strategy\_logger.py** | StrategyLogger | ✍️ **整形済み情報のログ記録** |
| **strategy\_notifier.py** | StrategyNotifier | 📧 **整形済み情報のメール通知** |

---

## **4\. 各モジュールの詳細仕様 🛠️**

### **4.1 strategy\_orchestrator.py**

|  |  |
| :---- | :---- |
| **クラス名** | DynamicStrategy |
| **責務** | 各専門コンポーネントを統括し、backtraderのイベントに応じて適切なモジュールを呼び出す司令塔。 |
| **主要メソッド** | \_\_init\_\_: 全ての専門コンポーネントをインスタンス化する。\<br\>next: データ更新のたびに、ポジションの有無に応じてシグナル生成器や決済ロジックを呼び出す。\<br\>notify\_order, notify\_trade: backtraderからのイベントを対応するハンドラ（EventHandler, PositionManager）に委譲する。 |
| **依存関係** | 全ての専門コンポーネントをインスタンス化して保持する。 |

### **4.2 strategy\_initializer.py**

|  |  |
| :---- | :---- |
| **クラス名** | StrategyInitializer |
| **責務** | 戦略パラメータ（YAML）に基づき、取引ロジックで必要となる全てのインジケーターオブジェクトを生成する。 |
| **主要メソッド** | create\_indicators: 設定ファイルからエントリー条件と決済条件を読み解き、必要なbacktraderインジケーターを動的に生成して返す。 |
| **依存関係** | なし。 |

### **4.3 entry\_signal\_generator.py**

|  |  |
| :---- | :---- |
| **クラス名** | EntrySignalGenerator |
| **責務** | 価格やインジケーターの状態に基づき、「買い」または「売り」の**エントリーシグナルを生成**することに特化する。状態を持たない。 |
| **主要メソッド** | check\_entry\_signal: エントリー条件を評価し、シグナル（'long'または'short'）とエントリー根拠（文字列）を返す。 |
| **依存関係** | StrategyInitializerが生成したインジケーター群。 |

### **4.4 exit\_signal\_generator.py**

|  |  |
| :---- | :---- |
| **クラス名** | ExitSignalGenerator |
| **責務** | 保有中のポジションに対し、利確や損切り条件を監視し、**決済（エグジット）シグナルを生成**する。 |
| **主要メソッド** | calculate\_and\_set\_exit\_prices: エントリー価格に基づき、具体的な利確・損切り価格を計算する。\<br\>check\_exit\_conditions: リアルタイム取引において、現在の価格が決済価格に達したかを判断し、達していればOrderManagerに決済を依頼する。 |
| **依存関係** | StrategyInitializerが生成したインジケーター群、OrderManager（決済依頼用）。 |

### **4.5 order\_manager.py**

|  |  |
| :---- | :---- |
| **クラス名** | OrderManager |
| **責務** | シグナルに基づき、リスク許容度から**注文サイズを計算**し、backtraderの**発注API（buy/sell/close）を実行**する。 |
| **主要メソッド** | place\_entry\_order: エントリーシグナルを受け、ロット計算を行い、新規注文を発注する。\<br\>place\_backtest\_exit\_orders: バックテスト時に利確・損切りのOCO注文を発注する。\<br\>close\_position: 決済注文を発注する。 |
| **依存関係** | StrategyOrchestrator（API実行用）、EventHandler（注文発注イベントの通知用）。 |

### **4.6 position\_manager.py**

|  |  |
| :---- | :---- |
| **クラス名** | PositionManager |
| **責務** | 現在保有しているポジションの**状態（サイズ、平均価格、エントリー日時など）を保持・管理**する。また、システム再起動時に永続化された**状態を復元**する。 |
| **主要メソッド** | restore\_state: 外部から与えられたポジション情報で、戦略の状態を復元する。\<br\>on\_trade\_update: notify\_tradeイベントを受け、ポジションの開始・終了に合わせて内部状態を更新する。 |
| **依存関係** | なし。 |

### **4.7 event\_handler.py**

|  |  |
| :---- | :---- |
| **クラス名** | EventHandler |
| **責務** | backtraderからの**イベント（注文約定、エラー等）を解釈**し、ログ記録や通知のための**メッセージ（文字列）を整形**する。 |
| **主要メソッド** | on\_order\_update: notify\_orderイベントを受け、注文ステータスに応じて適切なメッセージを組み立て、StrategyLoggerとStrategyNotifierに渡す。 |
| **依存関係** | StrategyLogger、StrategyNotifier。 |

### **4.8 strategy\_logger.py**

|  |  |
| :---- | :---- |
| **クラス名** | StrategyLogger |
| **責務** | 整形済みのメッセージを受け取り、**ログファイルに記録**することに特化する。 |
| **主要メソッド** | log: 指定されたレベルでメッセージをログに出力する。\<br\>log\_bar\_data: デバッグ用に毎tickの価格やインジケーター情報をログに出力する。 |
| **依存関係** | Pythonのloggingモジュール。 |

### **4.9 strategy\_notifier.py**

|  |  |
| :---- | :---- |
| **クラス名** | StrategyNotifier |
| **責務** | 整形済みのメッセージを受け取り、**メールなどの手段で外部に通知**することに特化する。 |
| **主要メソッド** | send: メッセージの件名と本文を受け取り、外部通知システム（core.util.notifier）に送信を依頼する。 |
| **依存関係** | core.util.notifier。 |

