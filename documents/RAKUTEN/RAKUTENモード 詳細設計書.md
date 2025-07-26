## **RAKUTENモード 詳細設計書**

### 1\. 概要

本設計書は、自動売買システムのリアルタイム取引機能「RAKUTENモード」に関する詳細な技術仕様を定義するものである。本モードは、楽天証券のトレーディングツール「マーケットスピード II RSS」とPythonアプリケーションを**Excelワークブックを介して連携**させることで、リアルタイムデータに基づいた取引判断を実現する。

### 2\. システムアーキテクチャ

本システムは、Pythonアプリケーション、Excel Hub、マーケットスピード II の3つの主要プロセスから構成される。

  - **データフロー**:
    1.  **価格データ**: マーケットスピード II のRSS関数が、リアルタイムの市場価格をExcel Hubの特定セルに継続的に書き込む。
    2.  **データ読取**: Pythonの`ExcelBridge`が、バックグラウンドスレッドでExcel Hubのセルを定期的にポーリングし、価格と口座情報を内部キャッシュに格納する。
    3.  **データ供給**: `RakutenData`が`ExcelBridge`のキャッシュからデータを取得し、`backtrader`エンジンが利用可能な形式で供給する。
    4.  **取引判断**: `DynamicStrategy`が供給されたデータに基づき、エントリーまたはクローズの判断を行う。
    5.  **注文シグナル**: `RakutenBroker`が`DynamicStrategy`からの売買指示を受け取り、**ログファイルに注文内容を出力**する。
    6.  **手動執行**: ユーザーはログファイルに出力されたシグナルを確認し、マーケットスピード II上で手動で発注を行う。

-----

### 3\. Excel Hub (`trading_hub.xlsm`) 仕様

PythonアプリケーションとRSS間のデータ交換を行うための中核ファイル。

#### 3.1. シート名: `リアルタイムデータ`

Pythonがポーリングする全てのデータをこのシートに集約する。

  - **市場データ**:

      - `A2:A10`列: **銘柄コード** (ユーザーが手入力)
      - `B2:B10`列: **現在値** (RSS関数: `=RSS(A2,"現在値")`)
      - `C2:C10`列: **始値** (RSS関数: `=RSS(A2,"始値")`)
      - `D2:D10`列: **高値** (RSS関数: `=RSS(A2,"高値")`)
      - `E2:E10`列: **安値** (RSS関数: `=RSS(A2,"安値")`)
      - `F2:F10`列: **出来高** (RSS関数: `=RSS(A2,"出来高")`)

  - **口座データ**:

      - `A11`セル: ラベルとして「**買付余力**」と入力
      - `B11`セル: **買付余力** (RSS関数: マーケットスピード II の口座情報取得関数を想定)

*(注: 上記は最大9銘柄の例。監視対象銘柄数に応じて範囲は拡張可能)*

-----

### 4\. Pythonモジュール詳細設計

#### 4.1. `ExcelBridge` (`src/realtrade/bridge/excel_bridge.py`)

Excel Hubとの通信をカプセル化し、スレッドセーフなアクセスを提供する。

  - **クラス**: `ExcelBridge`
  - **プロパティ**:
      - `workbook_path: str`: Excel Hubファイルへのパス。
      - `latest_data: dict`: ポーリングした最新データを格納するキャッシュ。
      - `lock: threading.Lock`: キャッシュへのスレッドセーフなアクセスを保証する。
      - `is_running: bool`: データ監視スレッドの実行状態を管理するフラグ。
      - `data_thread: threading.Thread`: データ監視を実行するバックグラウンドスレッド。
  - **メソッド**:
      - `__init__(self, workbook_path)`: プロパティを初期化する。
      - `start(self)`: `_data_loop`をバックグラウンドスレッドで開始する。
      - `stop(self)`: `is_running`フラグを`False`にし、スレッドの終了を待つ。
      - `_data_loop(self)`:
        1.  スレッド毎にCOMライブラリを初期化 (`pythoncom.CoInitialize()`)。
        2.  `xlwings`でExcel Hubを開く。
        3.  `while self.is_running`ループ内で、`リアルタイムデータ`シートの指定範囲（`A2:F10`および`B11`）を読み取る。
        4.  `lock`を使用して`latest_data`キャッシュをアトミックに更新する。
        5.  一定時間スリープする (例: 0.5秒)。
        6.  `finally`節でCOMライブラリを解放 (`pythoncom.CoUninitialize()`)。
      - `get_latest_data(self, symbol)`: `lock`を使用してキャッシュから指定銘柄のデータを安全に読み出し、コピーを返す。
      - `get_cash(self)`: `lock`を使用してキャッシュから買付余力を安全に読み出す。

#### 4.2. `RakutenData` (`src/realtrade/rakuten/rakuten_data.py`)

`ExcelBridge`をデータソースとする`backtrader`のカスタムデータフィード。

  - **クラス**: `RakutenData(bt.feeds.PandasData)`
  - **主要ロジック (`_load`メソッド)**:
    1.  `ExcelBridge`から最新データを取得する。
    2.  **価格変動の有無をチェック**: `ExcelBridge`から取得した`close`（終値）が、前回取得した`last_close`と同じか比較する。
    3.  **新規バー供給**: 価格に変動があった場合、新しいOHLCVデータでバーを生成し、`backtrader`エンジンに供給する (`return True`)。
    4.  **ハートビート供給**: 価格に変動がなかった場合、システムが停止しないように「ハートビート」バーを生成する。この際、**`high`に微小な値 (`epsilon`) を加算**し、`high`と`low`が同一値になるのを防ぐ。これにより、ADX等のインジケーターが値幅ゼロのデータで`ZeroDivisionError`を起こすのを防ぐ。

#### 4.3. `RakutenBroker` (`src/realtrade/rakuten/rakuten_broker.py`)

手動発注モードで動作する`backtrader`のカスタムブローカー。

  - **クラス**: `RakutenBroker(bt.brokers.BackBroker)`
  - **主要ロジック**:
      - `getcash(self)`: `ExcelBridge.get_cash()`を呼び出し、リアルタイムの買付余力を返す。これにより、戦略は常に最新の資金状況に基づいたLot計算が可能となる。
      - `buy(self, ...)` / `sell(self, ...)`: 実際の注文は執行せず、\*\*「【手動発注モード】買い(or 売り)シグナル発生」\*\*というメッセージと共に、銘柄、数量等の注文詳細をログに出力する。`backtrader`内部のポジション管理は親クラスのメソッドを呼び出すことで正常に行われる。

### 5\. エラーハンドリング

  - **Excel接続失敗**: `ExcelBridge`が起動時にExcel Hubに接続できない場合、クリティカルエラーとしてログに出力し、データ監視スレッドは安全に終了する。
  - **データ読取失敗**: ポーリング中にExcel Hubからのデータ読み取りに失敗した場合、エラーをログに出力し、`is_running`フラグを`False`にしてスレッドを終了させる。