# **株自動トレードシステム 詳細設計書 v6.0 (リアルタイム機能)**

## **1. 改訂履歴**

| バージョン | 改訂日 | 改訂内容 | 作成者 |
| :--- | :--- | :--- | :--- |
| **6.0** | **2025/07/02** | **バックテスト時のデグレード分析結果を反映。`btrader_strategy.py` (v17.1) の実装上の課題を「6. 既知の課題」として明記。** | Gemini |
| 5.0 | 2025/07/01 | リアルタイムトレードにおけるクライアントサイド決済ロジック（利確・トレーリングストップ）の実装を反映。 | Gemini |
| 4.0 | 2025/06/30 | `config_realtrade.py`の設定に基づき、モード（SBI/Yahoo/Mock）を切り替える実装を反映。Store/Broker/Dataパターンの導入と、それに伴うコンポーネント構成の更新。 | Gemini |
| 3.0 | 2025/06/29 | 状態永続化の責務をBrokerからAnalyzer (`TradePersistenceAnalyzer`) に移譲するアーキテクチャ変更を反映。カスタムブローカーを廃止し、設計を大幅に簡素化。 | Gemini |
| 2.0 | 2025/06/28 | v11.0/v77.0の最新実装を反映。戦略合成ロジック、Broker仕様を正式化。 | Gemini |
| 1.1 | 2025/06/26 | 複数銘柄・複数戦略対応の設計を反映 | Gemini |
| 1.0 | 2025/06/26 | 初版作成 | Gemini |

## **2. システム概要**

本システムは、証券会社のAPIと連携して株式の自動売買を行うものである。「共通設定(strategy.yml)」と「エントリー戦略カタログ(strategies.yml)」を動的に合成し、「戦略割り当て表(all_recommend_*.csv)」に基づいて各銘柄に適用する戦略を決定する。

リアルタイムトレードのシミュレーション（ドライラン）では、**`backtrader`標準のブローカー**が注文を処理し、**カスタムAnalyzer (`TradePersistenceAnalyzer`)** が取引イベントを監視して、ポジションの状態をデータベースに永続化する。これにより、実際のAPI連携を実装する前に、ロジックの正当性を安全かつ効率的に検証できる。

**v4.0では、システムの動作モードを柔軟に切り替える機構を導入した。`config_realtrade.py`の設定により、以下の3つのモードで動作する。**

1.  **SBI実取引モード (`LIVE_TRADING=True`, `DATA_SOURCE='SBI'`)**:
    SBI証券のAPIと直接連携し、実際の口座での発注およびデータ取得を行う。

2.  **Yahooデータ連携モード (`LIVE_TRADING=True`, `DATA_SOURCE='YAHOO'`)**:
    Yahoo Financeからリアルタイムの価格データを取得しつつ、発注処理は`backtrader`の内部ブローカーでシミュレーションする。売買ロジックの安全な検証に用いる。

3.  **完全シミュレーションモード (`LIVE_TRADING=False`)**:
    外部接続を一切行わず、内蔵のモックデータを使用して全機能のシミュレーションを実行する。

このマルチモードアーキテクチャにより、開発から本番稼働まで、一貫したコードベースで安全かつ効率的に対応することを可能にする。

v4.0で導入されたマルチモードアーキテクチャ（SBI実取引/Yahooデータ連携/完全シミュレーション）に加え、**v5.0ではリアルタイムトレードにおける決済ロジックの堅牢性を大幅に向上させた。**

多くの証券会社APIがネイティブのトレーリングストップ注文をサポートしていないという現実的な制約に対応するため、本システムは`live_trading`フラグによって決済ロジックを切り替えるデュアルモード方式を採用する。

* **バックテスト時**: `backtrader`ネイティブの`StopTrail`注文を使用し、理論上最も正確なパフォーマンスを測定する。
* **リアルタイムトレード時**: `Strategy`クラスがクライアントサイドで価格を常時監視し、利確・損切り条件を満たした時点で証券会社APIが確実に実行できる**成行注文**を発行する。

これにより、バックテストの再現性を可能な限り維持しつつ、現実の取引環境で確実かつ安全にポジションを決済することを可能にする。

## **3. システムアーキテクチャ (v5.0)**

### **3.1. コンポーネント構成図**

```mermaid
graph TD
    subgraph "設定レイヤー"
        A["<b>config_realtrade.py</b><br>(動作モード定義)"]
        B["<b>strategy.yml</b><br>(共通基盤)"]
        C["<b>strategies.yml</b><br>(エントリー戦略カタログ)"]
        D["<b>all_recommend_*.csv</b><br>(戦略割り当て表)"]
    end

    subgraph "実行レイヤー"
        E[メインコントローラー<br><b>run_realtrade.py</b>]

        subgraph "Cerebroエンジン"
            F[Cerebro<br><b>backtrader</b>]
            G[DynamicStrategy]
            H[TradePersistenceAnalyzer]
        end
        
        subgraph "データソース / Broker実装"
            direction TB
            subgraph " "
                I[SBIStore]
                J[SBIBroker]
                K[SBIData]
            end
            subgraph " "
                L[YahooStore]
                M[BackBroker]
                N[YahooData]
            end
            subgraph " "
                O[MockDataFetcher]
                P[BackBroker]
            end
        end

        subgraph "永続化レイヤー"
            Q[StateManager<br><b>realtrade/state_manager.py</b>]
            R[(SQLiteデータベース)]
        end

        A -->|読み込み| E
        B & C & D -->|読み込み| E
        E -->|初期化 & 登録| F
        
        F -- 実行 --> G
        F -- イベント通知 --> H

        G -- 注文発行 --> J
        G -- 注文発行 --> M
        G -- 注文発行 --> P
        H -- DB操作 --> Q
        Q <--> R
        
        E -- モード選択 --> I
        E -- モード選択 --> J
        E -- モード選択 --> K
        
        E -- モード選択 --> L
        E -- モード選択 --> M
        E -- モード選択 --> N

        E -- モード選択 --> O
        E -- モード選択 --> P

        I & L & O -->|データ供給| K & N & G
    end
    
    style E fill:#cce5ff,stroke:#b8daff
```

### **3.2. 処理フロー**

#### **3.2.1. 処理フロー (起動時)**

```mermaid
sequenceDiagram
    participant User as ユーザー
    participant Main as run_realtime.py
    participant Cfg as config_realtrade.py
    participant Cerebro as Cerebroエンジン
    participant Store as Store (SBI/Yahoo)
    participant Data as Data (SBI/Yahoo)
    
    User->>Main: `python run_realtrade.py` を実行
    Main->>Cfg: LIVE_TRADING, DATA_SOURCE を読み込み
    Main->>Main: 戦略関連ファイル (yml, csv) をロード
    
    alt LIVE_TRADING is True
        Main->>Store: store = (SBI/Yahoo)Store()
        Main->>Cerebro: broker = (SBI/Back)Broker(store)
        Main->>Cerebro: cerebro.setbroker(broker)
        loop 各銘柄
            Main->>Data: data_feed = (SBI/Yahoo)Data(store)
            Main->>Cerebro: cerebro.adddata(data_feed)
        end
    else LIVE_TRADING is False
        Main->>Cerebro: broker = BackBroker()
        Main->>Cerebro: cerebro.setbroker(broker)
        loop 各銘柄
            Main->>Cerebro: cerebro.adddata(MockData)
        end
    end
    
    Main->>Cerebro: cerebro.addanalyzer(TradePersistenceAnalyzer)
    Main->>Cerebro: cerebro.addstrategy(DynamicStrategy)
    Main->>Cerebro: cerebro.run() を実行
```

#### **3.2.2. 処理フロー (リアルタイムトレード時の決済)**

```mermaid
sequenceDiagram
    participant Strategy as DynamicStrategy
    participant Cerebro as Cerebroエンジン
    participant Broker as LiveBroker (SBIBroker)
    participant API as 証券会社API

    loop ポジション保有中
        Cerebro->>Strategy: next() を呼び出し
        Strategy->>Strategy: _check_live_exit_conditions() を実行
        alt 利確/損切り条件を満たした場合
            Strategy->>Broker: self.close() (成行決済注文)
            Broker->>API: 成行注文を送信
            API-->>Broker: 約定通知
            Broker-->>Strategy: notify_order() で通知
            Strategy->>Strategy: ポジション決済処理
        else 条件を満たさない場合
            Strategy->>Strategy: トレーリングストップ価格を更新
        end
    end
```

## **4. モジュール詳細設計 (v6.0)**

### **4.1. メインコントローラー (run_realtrade.py)**
* **クラス**: `RealtimeTrader`
* **責務**:
    * (v4.0から変更なし) システム全体の起動・停止シーケンスの管理。
    * (v4.0から変更なし) `config_realtrade.py`を読み込み、動作モードを決定する。
    * (v4.0から変更なし) `backtrader.Cerebro`エンジンをセットアップし、動作モードに応じて適切な`Store`, `Broker`, `Data`の各クラスをインスタンス化してCerebroに登録する。
    * (v4.0から変更なし) `TradePersistenceAnalyzer`（状態永続化）をCerebroに追加する。
    * **(更新)** `DynamicStrategy`をCerebroに追加する際、`config_realtrade.py`から読み取った`live_trading`フラグをパラメータとして渡す。

### **4.2. データソース連携モジュール (`realtrade/live/`)**
* **設計思想**:
    * **Store**: 外部APIとの通信（口座情報取得、発注、履歴データ取得など）を直接担当する。
    * **Broker**: `backtrader`の`BrokerBase`を継承し、`Store`を介して実際の取引を模倣・実行する。
    * **Data**: `backtrader`の`feeds`クラスを継承し、`Store`から取得した価格データをCerebroに供給する。
* **`realtrade/live/sbi_*.py`**:
    * **`SBIStore`**: SBI証券APIとの通信ロジックを実装。
    * **`SBIBroker`**: `SBIStore`を利用して発注・キャンセルなどを行うカスタムブローカー。
    * **`SBIData`**: `SBIStore`から取得した価格データをリアルタイムに供給するデータフィード。
* **`realtrade/live/yahoo_*.py`**:
    * **`YahooStore`**: `yfinance`ライブラリを利用して、Yahoo Financeから履歴データを取得するロジックを実装。（発注機能は持たない）
    * **`YahooData`**: `YahooStore`から取得した価格データをリアルタイムに供給するデータフィード。
    * **Broker**: `DATA_SOURCE='YAHOO'`の場合、`run_realtime.py`は`backtrader`標準の`BackBroker`を使用する。


### **4.3. 戦略実行クラス (btrader_strategy.py)**

* **クラス**: `DynamicStrategy`
* **責務**:
    * (変更なし) `run_realtime.py`から渡された戦略パラメータに基づき、インジケーター計算と**エントリー**条件評価を行う。
    * (変更なし) `__init__`で`live_trading`パラメータを受け取り、決済ロジックを切り替える準備をする。
    * **(更新)** `next()`メソッドで、まず保留中の注文がないかを確認するガード条件を設ける。その後、ポジションの有無に応じて処理を分岐する。
        * **ガード条件**: `self.entry_order` (保留中のエントリー注文) または `self.exit_orders` (有効な決済注文) が存在する場合、後続の処理を行わずメソッドを終了する。 **※この実装はバックテスト時に問題を引き起こす。詳細は「6. 既知の課題」を参照。**
        * **ポジションあり**: `live_trading=True`の場合、クライアントサイド決済ロジック (`_check_live_exit_conditions`) を呼び出す。
        * **ポジションなし**: エントリー条件を評価する (`_check_entry_conditions`)。
    * **(新規)** **クライアントサイド決済ロジック (`_check_live_exit_conditions`)**:
        * **利確(Take Profit)**: 現在価格がエントリー時に計算した利確価格 (`self.tp_price`) に達したか判定する。
        * **損切り(Stop Loss)**: ATRに基づいたトレーリングストップをシミュレートする。
            1.  現在価格が現在の損切り価格 (`self.sl_price`) に達したか判定する。
            2.  達していない場合、価格が有利な方向に動いていれば、損切り価格を更新する。
        * 上記いずれかの条件を満たした場合、`self.close()`を呼び出して**成行決済注文**を発行する。
    * **(新規)** **バックテスト用決済ロジック (`_place_native_exit_orders`)**:
        * エントリー注文約定後、`live_trading=False`の場合にのみ呼び出される。
        * `backtrader`ネイティブの`Order.Limit`（利確）と`Order.StopTrail`（損切り）をOCO注文として発行し、`self.exit_orders`リストに格納する。

### **4.4. 状態永続化アナライザー (realtrade/analyzer.py)**
* **クラス**: `TradePersistenceAnalyzer`
* **責務**: (変更なし)
    * `backtrader`の取引イベント(`notify_trade`)を監視する。
    * 取引の開始・終了を検知し、`StateManager`を通じてポジション状態をデータベースに永続化する。

### **4.5. 状態管理モジュール (realtime/state_manager.py)**
* **責務**: SQLiteデータベースとの接続、テーブルの作成、ポジション情報のCRUD（作成・読み取り・更新・削除）操作を提供する。（変更なし）

## **5. アーキテクチャ設計思想**

### **5.1. アーキテクチャ設計思想（v3.0での変更点）**

バージョン2.0までのカスタムブローカー (`BrokerBridge`) を利用した設計から、`backtrader`の標準ブローカーとカスタムアナライザーを組み合わせる設計へと変更した。

* **変更理由**:
    1.  **関心の分離**: 注文執行のシミュレーション（ブローカーの役割）と、その結果の永続化（アナライザーの役割）を明確に分離できる。
    2.  **`backtrader`への準拠**: `Analyzer`は、`backtrader`が公式にサポートするイベント監視・分析のための仕組みであり、フレームワークの思想に沿った自然な実装となる。
    3.  **コードの簡素化**: `get_notification`のような通知キューの管理や、注文状態の複雑なハンドリングを`backtrader`の標準ブローカーに任せることができるため、自作コードが大幅に削減され、堅牢性が向上する。

この変更により、将来実際の証券会社APIに接続する際も、この`TradePersistenceAnalyzer`を再利用または参考にすることで、スムーズな移行が期待できる。
### **5.2. アーキテクチャ設計思想（v4.0での変更点）**
* **モード分離による安全性と開発効率の向上**:
    * `config_realtrade.py`のフラグ一つで、本番環境・データ連携シミュレーション・完全シミュレーションを切り替えられるようにした。
    * これにより、実際の資金を動かすことなく、APIから取得した本物のデータでロジックを検証したり、外部接続なしでUIや基本機能の開発を進めたりすることが可能になる。

* **`Store / Broker / Data` パターンの採用**:
    * 証券会社ごとの実装を`realtrade/live`配下にカプセル化した。
    * API通信(Store)、取引執行(Broker)、データ供給(Data)という責務を分離することで、将来的に他の証券会社（例: 楽天証券）に対応する際、`realtrade/live/rakuten_*.py`を追加するだけで容易に拡張できる。

* **リアルタイム処理の堅牢化**:
    * `YahooData`フィードでは、バックグラウンドで価格データを取得するために独立した**デーモンスレッド**を使用する。これにより、メインプログラムが`Ctrl+C`などで終了した際に、データ取得スレッドも確実に追従して終了し、リソースリークを防ぐ。
    * `yfinance`から返されるデータ形式の揺らぎ（MultiIndexや重複カラム）に対応するため、データ供給前に整形・クリーニング処理を行い、システムの安定性を高めている。

### **5.3. v5.0での変更点 (決済ロジック)**
* **デュアルモード決済ロジックの採用**:
    * 多くの証券会社APIが、`StopTrail`（トレーリングストップ）のような高度な注文タイプをサポートしていない。この制約を吸収し、システムの汎用性と確実性を高めるため、バックテストとリアルタイムトレードで決済ロジックを分離した。
    * **バックテスト**では、`backtrader`のネイティブ注文を利用することで、スリッページや遅延のない「理想環境」での戦略パフォーマンスを正確に測定する。
    * **リアルタイムトレード**では、`Strategy`が自ら価格を監視し、決済条件を判定する「クライアントサイド・ロジック」を採用。これにより、APIがサポートする最も基本的な「成行注文」で決済を実行でき、ブローカーの実装に依存しない堅牢なシステムを実現する。

* **差異の許容とリスク管理**:
    * このアプローチでは、バックテストとリアルタイムトレードの間に、スリッページやデータ受信の遅延によるパフォーマンスの差異が必然的に生じる。
    * これはシステムの欠陥ではなく、現実の取引環境を反映するための意図的な設計上のトレードオフである。
    * リアルタイムトレードでは、「理論価格から多少ズレてでも、確実に決済を実行すること」を最優先とし、大きな損失リスクを回避する設計となっている。

## **5.4. v6.0での変更点 (v6.0)**

* **バックテストにおけるデグレードの発生 (v17.1)**:
    * **現象**: `btrader_strategy.py` (v17.1) を用いてバックテストを実行すると、各銘柄で最初の取引が決済されずにテスト期間の最後まで持ち越され、取引回数が大幅に減少するデグレードが発生し、対策済み。
    * **原因**: `next()`メソッドの先頭に実装されたガード条件 `if self.exit_orders:` が原因である。バックテストでは、エントリー後にネイティブの決済注文（`StopTrail`等）が発行され、`self.exit_orders`リストに格納される。このリストはポジションが決済されるまで空にならないため、`next()`メソッドが常に早期リターンしてしまう。これにより、`backtrader`エンジンによるネイティブ決済注文の判定処理がスキップされ、決済が行われない。
    * **対策**: `next()`メソッドのガード条件を、リアルタイムトレード時（クライアントサイドの成行注文を待機する場合）に限定して適用するよう修正した。具体的には、`if self.live_trading and self.exit_orders:` のように、ライブトレードモードでのみ決済注文の存在をチェックするロジックに変更した。
