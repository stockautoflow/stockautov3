# 株自動トレードシステム

責務分離の原則に基づきリファクタリングされた、Python製の株自動トレードシステムです。
システムは、分析、バックテスト、リアルタイム取引、可視化といった機能ごとに独立したコンポーネント群で構成されています。

## プロジェクト構成

```plaintext
/ (プロジェクトルート)
|
|-- config/
|   |-- strategy_base.yml      # 全戦略共通の基本設定 (出口戦略, 資金管理)
|   |-- strategy_catalog.yml   # 評価したいエントリー戦略のカタログ
|   +-- email_config.yml       # メール通知設定
|
|-- data/                      # 株価データ (CSV) を格納
|-- log/                       # 実行ログを格納
|-- results/
|   |-- backtest/              # 単一バックテストの結果
|   +-- evaluation/            # 全戦略評価の結果
|
|-- src/
|   |
|   |-- core/                  # 【共通部品】
|   |   |-- strategy.py        # 全コンポーネントで利用する戦略クラス (DynamicStrategy)
|   |   |-- indicators.py      # カスタムインジケーター
|   |   +-- util/
|   |       |-- logger.py      # ログ設定
|   |       +-- notifier.py    # メール通知機能
|   |
|   |-- backtest/              # 【単一バックテスト部品】
|   |   |-- run_backtest.py    # 実行スクリプト (python -m src.backtest.run_backtest)
|   |   |-- config_backtest.py # 単一バックテスト用の設定
|   |   +-- report.py          # 結果レポートの生成
|   |
|   |-- evaluation/            # 【全戦略評価・集計部品】
|   |   |-- run_evaluation.py  # 実行スクリプト (python -m src.evaluation.run_evaluation)
|   |   |-- orchestrator.py    # 全戦略のバックテストを順次実行・管理
|   |   +-- aggregator.py      # 各戦略のレポートを集計・統合
|   |
|   |-- realtrade/             # 【リアルタイム取引部品】
|   |   |-- run_realtrade.py   # 実行スクリプト (python -m src.realtrade.run_realtrade)
|   |   |-- config_realtrade.py# リアルタイム取引用の設定
|   |   |-- state_manager.py   # ポジション状態をDBで永続化
|   |   |-- analyzer.py        # 取引永続化のためのアナライザー
|   |   |-- live/              # 本番取引用のモジュール (各証券会社/データソース)
|   |   +-- mock/              # シミュレーション用のモックデータ生成
|   |
|   +-- dashboard/             # 【可視化ツール部品】
|       |-- app.py             # 実行スクリプト (python -m src.dashboard.app)
|       |-- chart_generator.py # Plotlyチャート生成ロジック
|       +-- templates/
|           +-- index.html     # ダッシュボードのHTMLテンプレート
|
|-- requirements.txt           # 依存ライブラリ
+-- .env.example               # APIキー設定のテンプレート
````

## セットアップ

#### 1\. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

#### 2\. データファイルの配置

`data/` ディレクトリに、バックテストや分析に必要な株価データ（CSV形式）を配置します。
ファイル名の形式は `config/strategy_base.yml` 内の `timeframes` セクションで定義します。

**例:**

  * `1332_D_2024.csv` (銘柄コード\_日足\_年)
  * `7203_60m_2025.csv` (銘柄コード\_60分足\_年)
  * `9984_5m_2025-06.csv` (銘柄コード\_5分足\_年月)

#### 3\. 設定ファイルの編集

`config/` ディレクトリ内の `.yml` ファイルを、用途に応じて編集します。

  * `strategy_base.yml`: 全戦略で共通の基本設定（時間足の定義、出口戦略、資金管理など）。
  * `strategy_catalog.yml`: 評価したいエントリー戦略のカタログ。ここに独自の戦略を追加できます。
  * `email_config.yml`: メール通知機能を使用する場合の設定。

#### 4\. APIキーの設定 (リアルタイム取引)

リアルタイム取引で証券会社のAPIを利用する場合は、`.env.example` をコピーして `.env` ファイルを作成し、APIキーとシークレットを記述します。

```bash
cp .env.example .env
```

`.env` ファイル内:

```
API_KEY="YOUR_API_KEY_HERE"
API_SECRET="YOUR_API_SECRET_HERE"
```

-----

## 各コンポーネントの実行方法

各コンポーネントは、プロジェクトのルートディレクトリから以下のコマンドで実行します。

### 1\. 全戦略の評価 (Evaluation)

`config/strategy_catalog.yml` に定義された全ての戦略を、`data/` 内の全銘柄データに対して横断的にバックテストし、結果を `results/evaluation/` に出力します。

**コマンド:**

```bash
python -m src.evaluation.run_evaluation
```

  * **主な成果物:**
      * `results/evaluation/{タイムスタンプ}/all_summary_*.csv`: 全戦略のパフォーマンスサマリー。
      * `results/evaluation/{タイムスタンプ}/all_trade_history_*.csv`: 全ての取引履歴。
      * `results/evaluation/{タイムスタンプ}/all_recommend_*.csv`: 銘柄ごとに最も成績の良かった戦略。

### 2\. 単一バックテスト (Backtest)

`config/strategy_base.yml` で定義された単一の戦略でバックテストを実行します。特定の戦略を詳細に分析したい場合に使用します。

**コマンド:**

```bash
python -m src.backtest.run_backtest
```

  * **主な成果物:**
      * `results/backtest/report/`: 個別バックテストのレポートが出力されます。

### 3\. 可視化ダッシュボード (Dashboard)

`evaluation` で得られた全取引履歴を、インタラクティブなチャートで可視化するWebアプリケーションを起動します。

**コマンド:**

```bash
python -m src.dashboard.app
```

  * 起動後、ブラウザで `http://127.0.0.1:5002` にアクセスしてください。
  * 銘柄や時間足、インジケーターのパラメータを動的に変更して分析できます。

### 4\. リアルタイム取引 (Real-time Trade)

`evaluation` で生成された推奨戦略 (`all_recommend_*.csv`) に基づき、リアルタイムでの取引（またはシミュレーション）を開始します。

**コマンド:**

```bash
python -m src.realtrade.run_realtrade
```

  * **モード切替:** `config/config_realtrade.py` の `LIVE_TRADING` フラグで、本番取引とシミュレーションを切り替えられます。
  * **データソース:** 同ファイル内の `DATA_SOURCE` で、`'SBI'` や `'YAHOO'` などのデータソースを選択します。
