はい、承知いたしました。
ご提示いただいたファイルと、「コンポーネント追加時に`main.py`と`run_merge.py`の両方を修正する必要がある」という根本的な課題を把握しました。

このメンテナンス性の問題を解決するため、アーキテクチャを再設計します。
以下に、新しいアーキテクチャの仕様案を提案します。

-----

## **新アーキテクチャ基本仕様**

### 1\. 現状の課題

  * **設定の重複**: コンポーネントの情報（名前、エイリアス、スクリプトパス）が`main.py`, `cli_config.yml`, `run_merge.py`に分散・重複して存在している。
  * **高いメンテナンスコスト**: 新しいコンポーネント（例: `create_new_feature.py`）を追加する際、複数の設定ファイルとスクリプトを修正する必要があり、手間がかかり、修正漏れのリスクも高い。
  * **拡張性の欠如**: 現状のままでは、コンポーネントが増えるほど管理が煩雑になり、スケールしない。

### 2\. 設計思想（コンセプト）

上記の課題を解決するため、以下の3つの原則に基づきアーキテクチャを再設計します。

1.  **コンポーネントの自動検出 (Component Auto-Discovery)**

      * コンポーネントの定義を、設定ファイルから\*\*ファイル名（命名規則）\*\*に移します。
      * `scripts/create_*.py` という命名規則に従うファイルをスキャンし、存在するコンポーネントを動的に認識します。これにより、ファイルを追加するだけでシステムがコンポーネントを自動で認識できるようになります。

2.  **設定の一元管理 (Centralized Configuration)**

      * 自動検出できない情報（エイリアス、`all`指定時の実行順序など）のみを、**単一のシンプルな設定ファイル** (`config.yml`) に集約します。
      * これにより、設定の重複と分散を完全に排除します。

3.  **責務の集約 (Consolidation of Responsibilities)**

      * `main.py`を唯一の**コマンドラインエントリーポイント**と位置づけます。
      * `run_merge.py`の役割（エイリアス解釈とスクリプト実行）は`main.py`に吸収させ、`run_merge.py`自体を**廃止**します。

### 3\. 新しいアーキテクチャの仕様

#### 3.1. ディレクトリ構造と命名規則 (Convention)

  * コンポーネントの定義は、`scripts/`ディレクトリ内のファイル名によって行います。
  * **命名規則**: `scripts/create_{component_name}.py`
      * 例: `scripts/create_core.py` は `core` コンポーネントを定義します。

#### 3.2. 新しい設定ファイル (`config.yml`)

`cli_config.yml`を廃止し、以下の新しい`config.yml`に置き換えます。このファイルは自動検出できない情報のみを保持します。

```yaml
# config.yml

# `gall`や`tmall`など、'all'指定で実行する際のコンポーネントの順序
component_order:
  - initialize
  - core
  - backtest
  - evaluation
  - rakuten
  - realtrade
  - dashboard
  - db

# 'python -m' で実行するモジュール定義
runnable_modules:
  backtest: "src.backtest.run_backtest"
  evaluation: "src.evaluation.run_evaluation"
  realtrade: "src.realtrade.run_realtrade"
  dashboard: "src.dashboard.app"

# コマンドのエイリアス定義
# キーがエイリアス、値が元のコマンド名
aliases:
  # メインコマンドのエイリアス
  g: generate
  r: run
  t: tool

  # コンポーネント名のエイリアス
  i: initialize
  c: core
  b: backtest
  e: evaluation
  rk: rakuten # 'r'はrunと重複するため変更
  rt: realtrade # 'r'はrunと重複するため変更
  d: dashboard
```

  * **ポイント**:
      * スクリプトパスの定義がなくなりました（自動検出するため）。
      * `run_merge.py`で定義されていたエイリアスもここに集約します。

#### 3.3. コンポーネント検出モジュール (`discover.py`)

`main.py`が利用する、コンポーネントを自動検出するための共有モジュールを新設します。

  * **ファイルパス**: `tools/discover.py`
  * **提供する関数**: `discover_components(script_dir="scripts")`
      * この関数は`script_dir`をスキャンし、`create_*.py`のパターンに一致するファイルを見つけます。
      * 戻り値: `{ "component_name": "path/to/script.py", ... }` 形式の辞書。
          * 例: `{'core': 'scripts/create_core.py', 'backtest': 'scripts/create_backtest.py'}`

#### 3.4. `main.py` の再設計

`main.py`は、起動時にコンポーネントを自動検出し、設定ファイルと組み合わせて動作します。

  * **起動シーケンス**:
    1.  `config.yml` を読み込む。
    2.  `discover.py`の`discover_components()`を呼び出し、利用可能な全コンポーネントとそのパスを取得する。
    3.  上記2つの情報から、`argparse`の選択肢（choices）を動的に生成する。
  * **コマンド処理**:
      * `generate`コマンド: `discover_components()`の結果から対象スクリプトのパスを取得し、`python <script_path>`を実行。
      * `run`コマンド: `config.yml`の`runnable_modules`からモジュール名を取得し、`python -m <module_name>`を実行。
      * `tool merge`コマンド: `discover_components()`の結果から対象スクリプトのパスを取得し、`python tools/merge/merge_changes.py <script_path>`を直接実行する。

#### 3.5. `run_merge.py` の廃止

このスクリプトの役割は`main.py`の`tool merge`コマンドに完全に吸収されるため、**ファイルごと削除します**。

#### 3.6. `merge_changes.py` の役割

このスクリプトは変更マージのコアエンジンとして**そのまま利用します**。呼び出し元が`run_merge.py`から`main.py`に変わるだけです。

### 4\. 期待される効果

  * **メンテナンス性の劇的な向上**:
      * **新しいコンポーネントの追加は、`scripts/create_new.py`を1つ作成するだけで完了します。** `main.py`や設定ファイルの修正は一切不要です。
      * エイリアスや実行順序の変更も、`config.yml`の修正のみで完結します。
  * **信頼性の向上**: 設定の重複をなくすことで、修正漏れや不整合といった人為的ミスを防ぎます。
  * **コードの簡素化**: `main.py`のロジックが「検出」と「実行」に特化し、`run_merge.py`が不要になることで、全体の見通しが良くなります。

-----

以上が提案する新しいアーキテクチャの仕様です。
この仕様に基づき、詳細設計や具体的な実装に進むことができます。ご検討ください。