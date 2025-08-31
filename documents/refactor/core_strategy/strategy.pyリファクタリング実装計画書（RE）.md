はい、承知いたしました。  
最終確定した設計書に基づき、具体的な作業手順を定めたリファクタリング実装計画書をMarkdown形式で作成します。

---

# **DynamicStrategy リファクタリング実装計画書**

## **1\. 概要**

### **1.1. 目的**

「リファクタリング設計書」に基づき、src/core/strategy.pyの分割実装を計画的かつ安全に進める。本計画書は、具体的な実装手順、既存コードからの移行方法、および完了後の検証方法を定義する。

### **1.2. 参照ドキュメント**

* DynamicStrategy リファクタリング設計書

---

## **2\. 事前準備**

1. **バージョン管理**: 現在の正常に動作するコードベースをGit等でコミットまたはブランチ作成する。  
2. **ディレクトリ作成**: src/core/配下にstrategy/ディレクトリを新規作成する。  
3. **旧ファイルのバックアップ**: src/core/strategy.pyをsrc/core/strategy\_old.pyのようにリネームし、参照用として残しておく。

---

## **3\. 実装ステップ**

実装は、依存関係の少ないコンポーネントから着手し、最後に全体を統合するボトムアップアプローチを推奨する。

### **Step 1: 空ファイルの作成 (スケルトン)**

src/core/strategy/ディレクトリ内に、設計書で定義された9つの空ファイルとクラス定義を作成する。

* strategy\_orchestrator.py (class DynamicStrategy)  
* strategy\_initializer.py (class StrategyInitializer)  
* entry\_signal\_generator.py (class EntrySignalGenerator)  
* exit\_signal\_generator.py (class ExitSignalGenerator)  
* order\_manager.py (class OrderManager)  
* position\_manager.py (class PositionManager)  
* event\_handler.py (class EventHandler)  
* strategy\_logger.py (class StrategyLogger)  
* strategy\_notifier.py (class StrategyNotifier)

### **Step 2: 独立コンポーネントの実装**

他のクラスへの依存が少ない、または無いクラスから実装を進める。

1. **strategy\_logger.py**: ログ記録のロジックを実装。  
2. **strategy\_notifier.py**: 通知送信のロジックを実装。  
3. **strategy\_initializer.py**: インジケーター生成ロジック (\_create\_indicators) をstrategy\_old.pyから移管する。

### **Step 3: コアロジックコンポーネントの実装**

取引判断や状態管理の中核を担うクラスを実装する。

1. **position\_manager.py**: ポジションの復元 (\_restore\_position\_state) と更新 (notify\_trade) のロジックを移管。  
2. **entry\_signal\_generator.py**: エントリー条件の評価ロジック (\_evaluate\_condition, \_check\_all\_conditions) を移管。  
3. **event\_handler.py**: イベント解釈ロジック (notify\_orderの本体) を移管。この時点では、\_\_init\_\_でStrategyLoggerとStrategyNotifierを受け取るように実装する。

### **Step 4: 連携コンポーネントの実装**

他のコンポーネントと密に連携するクラスを実装する。

1. **order\_manager.py**: 注文サイズ計算と発注API呼び出しのロジックを移管。EventHandlerを呼び出す処理も実装する。  
2. **exit\_signal\_generator.py**: 決済価格の計算と決済条件の判断ロジック (\_recalculate\_exit\_prices, \_check\_live\_exit\_conditions等) を移管。OrderManagerを呼び出す処理も実装する。

### **Step 5: オーケストレーターの実装と統合**

最後に、司令塔となるクラスを実装し、全コンポーネントを結合する。

1. **strategy\_orchestrator.py**:  
   * \_\_init\_\_内で、Step 2〜4で作成した全コンポーネントをインスタンス化し、依存関係を解決する。  
   * next, notify\_order, notify\_tradeの各メソッドを、専門コンポーネントへの処理委譲のみを行うシンプルな形に書き換える。

---

## **4\. 既存コードからの移行ガイド**

strategy\_old.pyの各メソッドは、以下のクラスに移行する。

| 元のメソッド (in strategy\_old.py) | → | 移行先クラス | 備考 |
| :---- | :---- | :---- | :---- |
| \_\_init\_\_ | → | DynamicStrategy, 他 | 各コンポーネントの\_\_init\_\_に分割・移管 |
| log, \_send\_notification | → | StrategyLogger, StrategyNotifier | それぞれの専門クラスにロジックを移管 |
| \_create\_indicators | → | StrategyInitializer |  |
| \_evaluate\_condition, \_check\_all\_conditions | → | EntrySignalGenerator |  |
| \_check\_entry\_conditions | → | OrderManager | サイズ計算と注文発注のロジック |
| notify\_order | → | EventHandler | イベント解釈と後続処理の呼び出し |
| notify\_trade | → | PositionManager | ポジション状態の更新 |
| \_place\_native\_exit\_orders | → | OrderManager | バックテスト用の決済注文発注 |
| \_check\_live\_exit\_conditions | → | ExitSignalGenerator | ライブ取引用の決済条件判断 |
| \_recalculate\_exit\_prices | → | ExitSignalGenerator |  |
| \_restore\_position\_state | → | PositionManager |  |
| next | → | DynamicStrategy | 処理の委譲のみを行う形に再実装 |

---

## **5\. 統合とテスト**

### **5.1. インポート文の更新**

以下のファイルで、DynamicStrategyのインポート文を新しいパスに修正する。

* src/backtest/run\_backtest.py  
* src/realtrade/run\_realtrade.py

変更前: from src.core import strategy as btrader\_strategy  
変更後: from src.core.strategy.strategy\_orchestrator import DynamicStrategy

### **5.2. 動作確認**

リファクタリングの成功は、外部から見た動作が変わらないことで確認する。

1. **バックテストによる検証**:  
   * リファクタリング**前**のコードでバックテスト（python \-m src.backtest.run\_backtest）を実行し、生成されたサマリーレポート（純利益、PF、勝率など）を保存する。  
   * リファクタリング**後**のコードで同じバックテストを実行する。  
   * 両者のサマリーレポートの結果が**完全に一致する**ことを確認する。  
2. **リアルタイム取引の動作確認**:  
   * run\_realtrade.pyをシミュレーションモードまたはペーパートレード環境で起動し、ログ出力や通知がリファクタリング前と同様に行われることを確認する。

## **6\. 完了定義**

以下の全ての項目が満たされた時点で、本リファクタリングは完了とする。

* \[ \] 9つの新しいファイルが設計通りに実装されている。  
* \[ \] src/core/strategy\_old.pyがプロジェクトから削除されている（または無効化されている）。  
* \[ \] 関連モジュールのインポート文が更新されている。  
* \[ \] バックテストの結果がリファクタリング前と完全に一致する。