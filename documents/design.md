# **統合仕様書 \- 株自動トレードシステム**

## **目次**

1. [**株自動トレードシステム 基本仕様書 (v73.7)**](#bookmark=id.o5ooo6au83ih)  
   * [1.1. システムの目的](#bookmark=id.at6hw0qajnn0)  
   * [1.2. 主な目標](#bookmark=id.vn77un1fq2kc)  
   * [2\. システム要件](#bookmark=id.y9ldpv1ybfj0)  
   * [3\. システム構成](#bookmark=id.8ngs3gg28xz)  
   * [4\. 運用フロー](#bookmark=id.lgzmwqhm3kkl)  
   * [5\. リスクと対策](#bookmark=id.7w8p96h659ke)  
   * [6\. 免責事項](#bookmark=id.t0fll6em07hw)  
2. [**株自動トレードシステム 詳細設計書 (v73.7)**](#bookmark=id.ow6qujnw28yu)  
   * [1.1. システムの目的](#bookmark=id.erlz8so24e3z)  
   * [1.2. アーキテクチャ](#bookmark=id.rs4n7mnx4bae)  
   * [2\. 環境構築手順](#bookmark=id.u78ikqe8xf5x)  
   * [3\. スクリプトの使用方法](#bookmark=id.scwzrecb7bme)  
   * [4\. モジュール別詳細仕様](#bookmark=id.bm7l2rwo3be0)  
3. [**チャート機能 詳細設計書 (v73.7)**](#bookmark=id.5tm171gou5as)  
   * [1.1. 機能の目的](#bookmark=id.lsvxukeqjo7m)  
   * [1.2. アーキテクチャ](#bookmark=id.ttm1l1rfjmas)  
   * [2\. インターフェース仕様](#bookmark=id.oyysxt78wrzq)  
   * [3\. 機能仕様詳細](#bookmark=id.hndhc77wkcjg)  
4. [**ATRトレーリングストップ 実装仕様書 (v73.7)**](#bookmark=id.zebnp213cijh)  
   * [1.1. 目的](#bookmark=id.oxaej8pd1azv)  
   * [1.2. 実装方針](#bookmark=id.fpv1v27911q6)  
   * [2\. strategy.yml 仕様](#bookmark=id.837hw3o6ycou)  
   * [3\. btrader\_strategy.py 実装仕様](#bookmark=id.3jx5wa8plas1)  
5. [**トレード戦略のカスタマイズ方法 (v73.7)**](#bookmark=id.5uqbpc12fr8a)  
   * [1\. エントリー条件の定義 (entry\_conditions)](#bookmark=id.xe1yypmfe9qo)  
   * [2\. イグジット条件の定義 (exit\_conditions)](#bookmark=id.tsy5jm8guaer)  
   * [3\. ポジションサイジングの定義 (sizing)](#bookmark=id.alantyur10yy)  
   * [4\. カスタマイズの手順](#bookmark=id.oa40o1mov18d)  
6. [**エントリー戦略アイデア集**](#bookmark=id.a6er08zff2l2)  
   * [はじめに](#bookmark=id.3r6c7fvq5a94)  
   * [カテゴリー1: トレンドフォロー戦略 (Trend Following)](#bookmark=id.n1uahhpslyfo)  
   * [カテゴリー2: 平均回帰戦略 (Mean Reversion)](#bookmark=id.35n694sh73i9)  
   * [カテゴリー3: ボラティリティブレイクアウト戦略 (Volatility Breakout)](#bookmark=id.z8le2ht4589u)  
   * [カテゴリー4: 複合戦略 (Hybrid Strategies)](#bookmark=id.q119ha1mzzuq)

# **株自動トレードシステム 基本仕様書 (v73.7)**

## **1\. 概要**

### **1.1. システムの目的**

本システムは、高機能なバックテストフレームワーク **Backtrader** と、インタラクティブなグラフ描画ライブラリ **Plotly** を利用し、取引戦略の有効性を効率的かつ詳細に検証することを目的とする。マルチタイムフレーム分析に基づいた戦略を、コストやリスクを考慮して評価し、その結果を**Webブラウザ上で対話的に分析**することで、戦略改善のサイクルを高速化する。

### **1.2. 主な目標**

* **完全な戦略定義の外部化**: Pythonコードを編集することなく、設定ファイル（strategy.yml）の記述を変更するだけで、**エントリー、イグジット（損切り/利確）、ポジションサイズ計算**の全てを組み合わせ、柔軟に定義・検証できる。  
* **現実的なシミュレーション**: 取引手数料やスリッページを考慮し、より実践に近い損益を算出する。バックテスト期間終了時に未決済のポジションも、最終終値で評価・計上される。  
* **高度な決済注文**: BacktraderのネイティブOCO（One-Cancels-Other）注文とトレーリングストップ（StopTrail）機能を活用し、信頼性の高い決済ロジックを実現する。  
* **高度な分析UI**:  
  * **Webアプリケーション**: FlaskをWebサーバーとし、ブラウザから [http://127.0.0.1:5001](http://127.0.0.1:5001) にアクセスすることで分析ツールを起動する。  
  * **動的チャート**: Webページ上で銘柄や時間足を選択すると、チャートが動的に切り替わる。  
  * **パラメータ調整**: 以下のテクニカル指標のパラメータをWebフォームからリアルタイムに変更し、チャートに即時反映させることができる。  
    * 単純移動平均線 (SMA)  
    * 指数平滑移動平均線 (EMA)  
    * ボリンジャーバンド  
    * MACD  
    * RSI  
    * ストキャスティクス  
    * ADX / DMI  
    * ATR  
    * 一目均衡表  
    * VWAP (出来高加重平均価格)  
  * **チャートと取引履歴の連動**: 取引履歴テーブルの行をクリックすると、チャート上の該当期間がハイライトされ、視覚的な分析を支援する。  
* **設定の外部化**: 戦略ロジック、UIのデフォルトパラメータ、メール設定をYAMLファイルで管理し、保守性を確保する。

## **2\. システム要件**

### **2.1. 機能要件**

|  | 機能分類 | 機能概要 |
| :---- | :---- | :---- |
| データ処理 | dataディレクトリに配置されたCSV形式の株価ファイル（5分足）を起動時に読み込む。 |  |
| バックテスト実行 | run\_backtrader.pyを実行し、strategy.ymlに定義された戦略ロジックに基づき全銘柄のバックテストを行い、結果をCSVレポートとして出力する。 |  |
| Webアプリケーション | app.pyを実行することでFlaskサーバーを起動し、Webブラウザ上でチャート分析機能を提供する。 |  |
| インタラクティブチャート | ・銘柄、時間足、インジケーターのパラメータをWebUIから動的に変更可能。 ・チャートはマウス操作で拡大・縮小・移動が可能。 ・マウスホバーで日時、四本値、各インジケーターの値をツールチップで表示。 ・取引履歴テーブルとチャートが連動し、クリックでハイライト表示。 |  |
| 結果出力 | バックテスト実行時に、backtest\_results/reportディレクトリにサマリー、銘柄別詳細、統合取引履歴のCSVレポートを生成する。 |  |
| 通知・ログ機能 | システムの動作状況やエラーをログファイルに出力する。 |  |

### **2.2. 非機能要件**

| 要件項目 | 内容 |
| :---- | :---- |
| 操作性 | 利用者はrun\_backtrader.pyでバックテストを行い、app.pyで分析用Webサーバーを起動する。実際の分析はWebブラウザのGUIで行う。 |
| 拡張性 | 取引戦略の全ロジック（エントリー、イグジット、サイジング）をstrategy.ymlで管理。インジケーターのリアルタイムな調整はWeb UIから可能。 |
| 保守性 | システム設定、戦略ロジック定義、Webサーバー、チャート生成機能などをファイル分割し、可読性とメンテナンス性を高める。 |
| 信頼性 | BacktraderとPlotlyという、実績のあるライブラリを基盤とすることで、計算と描画の信頼性を確保する。 |

## **3\. システム構成**

### **3.1. アーキテクチャ図（概念）**

\[strategy.yml\] \<---+  
|  
\[CSVデータ\] \<---+ |  
| |  
\[run\_backtrader.py\] \---+--\> \[btrader\_strategy.py\] \---\> \[CSVレポート\] \<---+  
| |  
\+------------------------------------------------\> \[ログファイル\] |  
|  
\[app.py (Flask Webサーバー)\] \<----+-------------------------------------\> \[Webブラウザ (クライアント)\]  
| ^  
\+-------------\> \[chart\_generator.py (ライブラリ)\] \-----------------------+

### **3.2. 技術スタック**

| 領域 | 主要技術 | 役割 |
| :---- | :---- | :---- |
| プログラミング言語 | Python | システム全体の開発言語。 |
| Webフレームワーク | Flask | チャート分析機能を提供するWebサーバー。 |
| バックテストエンジン | Backtrader | バックテストの実行、指標計算、結果分析のコア機能。 |
| データ操作 | Pandas | CSVデータの読み込みと加工、レポート生成。 |
| チャート描画 | Plotly | インタラクティブなHTMLチャートのデータ生成。 |
| 設定ファイル | YAML | strategy.yml で戦略ロジックと各種設定を管理。 |

## **4\. 運用フロー**

1. **データ準備**: dataディレクトリに分析したい銘柄の5分足CSVデータを配置する。  
2. **戦略の定義**: strategy.ymlファイルを編集し、エントリー、イグジット、サイジングのルールを記述する。  
3. **バックテスト実行**: コマンドプロンプトで python run\_backtrader.py を実行する。  
4. **分析サーバー起動**: コマンドプロンプトで python app.py を実行する。  
5. **ブラウザで分析**: Webブラウザで [http://127.0.0.1:5001](http://127.0.0.1:5001) を開き、以下の操作を行う。  
   * ドロップダウンで銘柄と時間足を切り替え。  
   * 入力フォームでインジケーターのパラメータをリアルタイムに変更。  
   * 取引履歴テーブルをクリックして、チャート上の取引をハイライト。  
6. **結果確認**: backtest\_results/report内のCSVレポートで、数値的なパフォーマンスを確認する。  
7. **分析と改善**: 分析結果を基に、strategy.ymlの戦略定義を改善し、再度バックテストを実行する。

## **5\. リスクと対策**

| リスク | 対策 |
| :---- | :---- |
| 戦略ロジックのバグ | trade\_historyレポートで、意図した通りの「エントリー根拠」で取引が行われているかを確認する。ログファイルで取引前後の資金変動やインジケーターの値を追う。 |
| 過学習（カーブフィッティング） | 同じデータセットでパラメータ調整を繰り返すと、そのデータにのみ過度に最適化されてしまう。定期的に新しい期間のデータでテストを行い、戦略の堅牢性を確認する。 |
| CSVデータのフォーマットエラー | システムが想定するカラム名（datetime, open, high, low, close, volume）と日付形式 (YYYY-MM-DD HH:MM:SS) にデータが従っていることを確認する。 |

## **6\. 免責事項**

本システムは、特定の投資成果を保証するものではない。本システムを利用した結果生じたいかなる金融上の損失についても、開発者は一切の責任を負わないものとする。投資に関する最終的な決定は、利用者自身の判断と責任において行うこと。

# **株自動トレードシステム 詳細設計書 (v73.7)**

## **1\. 概要**

### **1.1. システムの目的**

本システムは、**Backtrader**による堅牢なバックテスト機能と、**Flask \+ Plotly**によるインタラクティブな分析UIを組み合わせ、取引戦略の検証と改善サイクルを高速化することを目的とする。

### **1.2. アーキテクチャ**

システムは、以下の3つの主要コンポーネントで構成される。

1. **バックテストエンジン (run\_backtrader.py, btrader\_strategy.py)**: strategy.ymlに定義されたルールを動的に解釈してバックテストを実行し、結果をCSVレポートに出力する。  
2. **Webアプリケーションサーバー (app.py)**: Flaskをベースとし、ブラウザからのリクエストに応じてチャート生成モジュールを呼び出し、結果を動的に表示するWebページを提供する。  
3. **チャート生成モジュール (chart\_generator.py)**: app.pyからライブラリとして呼び出され、価格データとインジケーターパラメータに基づき、PlotlyのグラフオブジェクトをJSON形式で生成する。

## **2\. 環境構築手順**

1. **プロジェクトファイルの配置**: 全ファイルを単一のディレクトリに配置する。  
2. **仮想環境の構築 (推奨)**:  
   python \-m venv venv  
   .\\venv\\Scripts\\activate  \# Windowsの場合  
   \# source venv/bin/activate  \# macOS/Linuxの場合

3. **ライブラリのインストール**:  
   pip install \-r requirements.txt

## **3\. スクリプトの使用方法**

1. **バックテストの実行（取引履歴の更新が必要な場合）**:  
   python run\_backtrader.py

2. **Web分析ツールの起動**:  
   python app.py

3. **ブラウザでアクセス**:  
   * Webブラウザで [http://127.0.0.1:5001](http://127.0.0.1:5001) を開く。

## **4\. モジュール別詳細仕様**

### **4.1. requirements.txt**

* **役割**: プロジェクトの実行に必要なPythonライブラリとそのバージョンを定義する。  
* **主要な内容**:  
  * backtrader: バックテストのコアエンジン。  
  * pandas, numpy: データ分析と数値計算。  
  * PyYAML: 設定ファイルの読み込み。  
  * plotly: インタラクティブチャートのデータ生成。  
  * Flask: Webアプリケーションサーバー機能。

### **4.2. config\_backtrader.py**

* **役割**: システム全体で共有される静的な設定値を管理する。  
* **主要な内容**:  
  * **ディレクトリパス**: DATA\_DIR, RESULTS\_DIR, LOG\_DIR, REPORT\_DIR, CHART\_DIRを定義。  
  * **バックテスト共通設定**: INITIAL\_CAPITAL（初期資金）、COMMISSION\_PERC（手数料率）、SLIPPAGE\_PERC（スリッページ率）などを定義。  
  * **ロギング設定**: LOG\_LEVELでログの詳細度（INFOまたはDEBUG）を制御する。

### **4.3. strategy.yml**

* **役割**: 取引戦略の**ロジックとパラメータ**を人間が編集しやすい形式で一元管理する。  
* **主要な内容**:  
  * trading\_mode: ロング/ショート戦略の有効/無効を切り替える。  
  * timeframes: 長期・中期・短期の時間足と圧縮率を定義。  
  * entry\_conditions: **エントリー戦略のコアロジックを定義する。**  
  * exit\_conditions: ATRに基づいた**損切り・利確ルール**を定義する。stop\_lossでは固定損切り(atr\_multiple)とトレーリング損切り(atr\_stoptrail)を選択可能。  
  * sizing: 1トレードあたりのリスク許容度に基づいた**ポジションサイズ計算ルール**を定義する。  
  * indicators: Web UIで表示する各テクニカル指標の**表示上のデフォルト値**を定義する。**バックテストのロジックには直接影響しない。**

### **4.4. email\_config.yml**

* **役割**: メール送信に関する機密情報（ID、パスワード等）をコード本体から分離し、セキュリティを確保する。  
* **主要な内容**:  
  * ENABLED: メール通知機能の有効/無効を切り替えるフラグ。  
  * SMTP\_SERVER, SMTP\_PORT: 送信に使用するメールサーバーの情報。  
  * SMTP\_USER, SMTP\_PASSWORD: 認証情報。  
  * RECIPIENT\_EMAIL: 通知を受け取るメールアドレス。

### **4.5. logger\_setup.py**

* **役割**: Python標準のloggingモジュールを設定し、一元的なログ管理機能を提供する。コンソールとファイルの両方に出力する。  
* **主要な内容**: setup\_logging()  
  * 実行時のタイムスタンプに基づき、log/backtest\_YYYY-MM-DD-HHMMSS.logというユニークなファイル名を生成する。  
  * ログのフォーマットを「時間 \- レベル \- モジュール名 \- メッセージ」に統一する。  
  * ログの出力先を、コンソール（画面）と上記ログファイルの両方に設定する。

### **4.6. notifier.py**

* **役割**: email\_config.ymlに基づき、バックテスト完了時にメール通知を行う。  
* **主要な内容**: send\_email(subject, body)  
  * email\_config.ymlを読み込み、通知が有効になっているか確認する。  
  * 有効な場合、Python標準のsmtplibを使い、設定情報に基づいてメールを作成し送信する。

### **4.7. btrader\_strategy.py**

* **役割**: strategy.ymlを動的に解釈する汎用的な戦略実行エンジン。  
* **主要な内容**:  
  * \_\_init\_\_: 戦略で使用する全インジケーターを事前に一度だけインスタンス化し、辞書に保持する。  
  * \_evaluate\_condition: YAMLに定義された単一の条件（例: ema \> closeやema1 crossover ema2）を評価するヘルパー関数。  
  * next:  
    * **ポジションがない場合**: \_check\_all\_conditions()を呼び出し、エントリー条件を評価。条件が満たされた場合、sizingとexit\_conditionsに基づき**リスク計算、ポジションサイズ、損切り/利確価格を決定**し、エントリー注文 (self.buy()/self.sell()) を発注する。  
  * notify\_order:  
    * 注文状態を監視し、ログを出力する。  
    * エントリー注文が約定した場合、定義されていれば**OCOで連携された損切り注文と利確注文を続いて発注**する。  
  * notify\_trade:  
    * トレード開始時(isopen)に、そのトレードの**正確な約定数量**(trade.size)と**エントリー根拠**(self.entry\_reason)を変数に保存する。  
    * トレード完了時(isclosed)に、開始時に保存した数量とエントリー根拠をtradeオブジェクトにカスタム属性としてアタッチする。これにより、TradeListアナライザーが正しい情報を取得できるようになる。

### **4.8. report\_generator.py**

* **役割**: 複数のバックテスト結果を集約し、人間が読みやすい形式の総合サマリーレポートを生成する。  
* **主要な内容**:  
  * 全銘柄のraw\_statsリストとstrategy.ymlのパラメータを受け取る。  
  * 純利益、勝率、プロフィットファクターなどのパフォーマンス指標を**全体で合算・再計算**する。  
  * 計算結果に基づき、「総損益」「勝率」などに対する定性的な評価コメントを生成する。  
  * strategy.ymlからエントリー/イグジットロジックの説明文を動的に生成する。  
  * これら全ての情報を整形し、最終的なpandas.DataFrameとして返す。

### **4.9. run\_backtrader.py**

* **役割**: バックテスト全体の実行を管理し、レポートファイル（CSV）を出力する。  
* **主要な内容**:  
  * TradeList(bt.Analyzer): 取引履歴を詳細に記録するためのカスタムアナライザー。  
    * notify\_trade: 決済済みトレードの情報を記録する。**数量**と**エントリー根拠**は、btrader\_strategyがtradeオブジェクトに付与したカスタム属性から取得する。  
    * stop: バックテスト終了時に未決済のポジションが残っている場合、その時点の終値で強制決済されたものとみなし、損益を計算する。**手数料はconfig.COMMISSION\_PERCから手動で正しく計算される。**  
  * run\_backtest\_for\_symbol: 単一銘柄のバックテストを実行し、アナライザーから結果を抽出して返す。  
  * main: dataディレクトリ内の全CSVファイルに対してループ処理を行い、report\_generatorを呼び出して3種類のレポート（サマリー、詳細、取引履歴）をCSVファイルとして保存する。

### **4.10. app.py (Webアプリケーションサーバー)**

* **役割**: Flaskサーバーを起動し、フロントエンドとバックエンドの橋渡しを行う。  
* **主要なエンドポイント**:  
  * @app.route('/'): メインページ (index.html) を描画する。  
  * @app.route('/get\_chart\_data'): ブラウザからの非同期リクエストを受け付け、chart\_generatorを呼び出してチャートと取引履歴のJSONデータを返すAPI。  
* **起動処理**: サーバー起動時にchart\_generator.load\_data()を一度だけ呼び出し、価格データと取引履歴をメモリにキャッシュする。

### **4.11. templates/index.html (フロントエンドUI)**

* **役割**: ユーザーインターフェースの構造を定義し、チャートの動的更新ロジックを実装する。  
* **主要なコンポーネント**:  
  * **コントロールパネル**: 銘柄と時間足の選択、および各インジケーターのパラメータ変更フォームを配置。  
  * **チャート表示領域**: Plotlyのグラフが描画される\<div\>タグ。  
  * **取引履歴テーブル**: チャートの下部に配置。  
* **主要なJavaScriptロジック**:  
  * updateChart(): コントロールパネルの値をAPIに送信し、返されたJSONでチャートとテーブルを更新する。  
  * highlightTradeOnChart(): テーブル行のクリックに連動し、チャート上の取引期間をハイライトする。

### **4.12. chart\_generator.py (チャート生成モジュール)**

* **役割**: app.pyから呼び出されるライブラリとして、Plotlyのグラフオブジェクトを生成する。  
* **主要な関数**:  
  * load\_data(): アプリケーション起動時に一度だけ呼ばれ、必要なCSVデータをキャッシュに読み込む。  
  * generate\_chart\_json(): キャッシュから価格データを取得し、リクエストされたパラメータに基づき各種テクニカル指標を動的に計算し、Plotlyのグラフオブジェクトを構築してJSON形式で返す。  
  * get\_trades\_for\_symbol(): キャッシュから指定された銘柄の取引履歴データを抽出して返す。

# **チャート機能 詳細設計書 (v73.7)**

## **1\. 概要**

### **1.1. 機能の目的**

本機能は、バックテスト結果を視覚化し、戦略の挙動を直感的に分析するためのインタラクティブなチャートをWebブラウザ上に提供することを目的とする。利用者は、銘柄、時間足、テクニカル指標のパラメータをWeb UIからリアルタイムに変更し、その結果を即座にチャートで確認できる。

### **1.2. アーキテクチャ**

* **フロントエンド**: HTML, CSS, JavaScriptで構成される単一のWebページ (templates/index.html)。  
* **バックエンド**:  
  * **Flask (app.py)**: Webサーバーとして機能し、ブラウザからのリクエストを処理する。  
  * **Plotly (chart\_generator.py)**: Flaskからの要求に応じて、チャートデータをJSON形式で生成する。  
* **データフロー**:  
  1. ブラウザがページを読み込むか、UIのフォームを変更する。  
  2. JavaScriptが現在の全設定値を取得し、/get\_chart\_data APIに非同期リクエストを送信する。  
  3. app.pyがリクエストを受け取り、パラメータをchart\_generator.pyに渡す。  
  4. chart\_generator.pyがチャートデータと取引履歴を生成し、JSONでapp.pyに返す。  
  5. app.pyが受け取ったJSONをブラウザに返す。  
  6. JavaScriptがJSONを受け取り、Plotly.jsライブラリを使ってチャートを描画・更新する。

## **2\. インターフェース仕様**

### **2.1. 入力 (バックエンド)**

* **strategy.yml**: 各種インジケーターの**表示上のデフォルトパラメータ**を定義。  
* **data/\*.csv**: 価格データ。  
* **backtest\_results/report/trade\_history\_\*.csv**: バックテストによる取引履歴。

### **2.2. 出力 (フロントエンド)**

* ブラウザ上に動的にレンダリングされるインタラクティブなチャート。物理的なファイル出力は行わない。

## **3\. 機能仕様詳細**

### **3.1. 基本チャート機能**

|  | 機能 | 仕様 |
| :---- | :---- | :---- |
| ローソク足 | 陽線は赤、陰線は緑で表示。 |  |
| 出来高 | ローソク足の色に連動した棒グラフとして、価格チャートの第2Y軸に半透明（opacity: 0.3）で描画。 |  |
| ズーム | マウスホイールのスクロールで拡大・縮小が可能 (scrollZoom: true)。 |  |
| パン（移動） | チャートをドラッグして表示範囲を移動可能。 |  |
| ツールチップ | Plotly標準の統一ツールチップ (hovermode: 'x unified') を使用。マウスカーソル位置の全データをまとめて表示する。 |  |
| 時間軸の最適化 | 短期・中期チャートでは、週末・夜間・昼休みを時間軸から除外（rangebreaks）し、取引時間のみを連続して表示。長期（日足）チャートでは週末のみを除外する。 |  |

### **3.2. インジケーター・取引表示**

| 機能 | 仕様 |
| :---- | :---- |
| 単純移動平均線 (SMA) | 全時間足に対応。短期・長期のSMAを価格チャートに重ねて描画。期間はWebフォームから変更可能。 |
| 指数平滑移動平均線 (EMA) | 全時間足に対応。長期EMAおよび短期EMA（速・遅）を価格チャートに重ねて描画。期間はWebフォームから変更可能。 |
| ボリンジャーバンド | 全時間足に対応。価格チャートに重ねて描画。期間と標準偏差はWebフォームから変更可能。バンド間は半透明のグレーで塗りつぶされる。 |
| VWAP | \*\*日中足（短期・中期）\*\*に対応。価格チャートに点線で描画。Webフォームのチェックボックスで表示/非表示を切り替え可能。 |
| 一目均衡表 | 短期チャートのみ対応。転換線、基準線、遅行スパン、先行スパンA、先行スパンBをそれぞれ線で描画。パラメータはWebフォームから変更可能。 |
| MACD | 短期チャートの下部パネルに描画。ヒストグラム、MACD線、シグナル線を表示。パラメータはWebフォームから変更可能。 |
| Slow Stochastic | 短期チャートの下部パネルに描画。%K線と%D線、および80/20の閾値ラインを表示。パラメータはWebフォームから変更可能。 |
| RSI | 中期チャートの下部パネルに描画。RSI線と70/30の閾値ラインを表示。パラメータはWebフォームから変更可能。 |
| ADX/DMI | 全時間足に対応。下部パネルにADX、+DI、-DIを線で描画。期間はWebフォームから変更可能。 |
| ATR | 全時間足に対応。下部パネルにATRを線で描画。期間はWebフォームから変更可能。 |
| 売買ポイント | 取引があった箇所にマーカーを表示（BUY: 赤▲, SELL: 緑▼）。 |
| 損切り・利確ライン | 各トレードに対応するSL/TPラインを点線で表示。 |

### **3.3. 画面レイアウト**

* **コントロールパネル**: 画面上部に配置。銘柄・時間足の選択ドロップダウンと、全インジケーターのパラメータ入力フォームを機能ごとにグループ化して配置。  
* **チャートパネル**: 画面中央の大部分を占める。価格チャートと、選択された時間足に応じたインジケーターのサブプロット（最大5段）で構成される。  
* **取引履歴テーブル**: 画面下部に配置。選択中の銘柄の全取引履歴を一覧表示し、クリックでチャート上の取引をハイライトする。テーブルが画面幅を超える場合は水平スクロールが可能。

# **ATRトレーリングストップ 実装仕様書 (v73.7)**

## **1\. 概要**

### **1.1. 目的**

利益を自動で追従（トレール）させながら損失を限定する、よりダイナミックな決済戦略を可能にするため、**ATRトレーリングストップ**機能を実装する。これにより、トレンド相場での利益最大化を目指す。

### **1.2. 実装方針**

ATRトレーリングストップは、Backtraderの**ネイティブ機能**であるbt.Order.StopTrailとOCO（One-Cancels-Other）注文を活用して実現されている。これにより、手動での価格追従ロジックを排除し、信頼性とシンプルさを向上させた。

1. **strategy.ymlの拡張**: exit\_conditions.stop\_lossセクションのtypeキーでatr\_stoptrailを指定できるようにした。  
2. **btrader\_strategy.pyの改修**: エントリー注文の約定後(notify\_order)に、利確注文（Limit）とトレーリングストップ注文（StopTrail）を**OCO注文として一度だけ発注**するロジックに変更した。

## **2\. strategy.yml 仕様**

exit\_conditions.stop\_lossセクションで設定する。

### **2.1. 設定項目**

| キー | 説明 | 設定例 |
| :---- | :---- | :---- |
| type | atr\_stoptrail を指定する。(atr\_multipleで固定損切り) | atr\_stoptrail |
| timeframe | ATRの計算に使用する時間足を指定します。（short, medium, long） | short |
| params.period | ATRの期間。 | 14 |
| params.multiplier | ATRの倍率。trailamount（トレール幅）として使用される。 | 2.5 |

### **2.2. 設定例**

\# strategy.yml

exit\_conditions:  
  \# 利確は固定ATR、もしくはこのセクション自体を削除することも可能  
  take\_profit:  
    type: "atr\_multiple"  
    timeframe: "short"  
    params: { period: 14, multiplier: 5.0 }

  \# 損切りロジックをトレーリングストップに変更  
  stop\_loss:  
    type: "atr\_stoptrail"         \# \<-- ネイティブトレーリングストップを指定  
    timeframe: "short"            \# ATRを計算する時間足  
    params:  
      period: 14                \# ATRの期間  
      multiplier: 2.5           \# ATRの倍率

## **3\. btrader\_strategy.py 実装仕様**

### **3.1. 主要な変更点**

* **注文方式の変更**: next()メソッドでの手動トレーリングロジックを完全に廃止。  
* **ネイティブOCO注文**: notify\_order()内で、エントリー約定後に利確注文とStopTrail注文をOCOで連携させる方式に変更。

### **3.2. 実装詳細**

#### **3.2.1. エントリー処理 (nextメソッド内)**

* ポジションがない場合、strategy.ymlのエントリー条件を評価する。  
* 条件が成立した場合、self.buy()またはself.sell()で**成行のエントリー注文のみを発注**する。  
* この時点ではまだ決済注文は発注されない。

#### **3.2.2. 決済注文の発注 (notify\_orderメソッド内)**

* エントリー注文 (self.entry\_order) の約定を検知する (order.status \== order.Completed)。  
* 約定後、\_place\_exit\_orders()メソッドが呼び出され、以下の注文が**直ちに発注**される。  
  1. **利確注文 (オプション)**: take\_profitが定義されていれば、exectype=bt.Order.Limitの注文が\*\*送信保留 (transmit=False)\*\*で作成される。  
  2. **トレーリングストップ注文**: exectype=bt.Order.StopTrailの注文が発注される。この際、oco引数に上記1の利確注文を渡すことで、2つの注文が自動的に連携される。  
* これにより、どちらか一方が約定すれば、もう一方は自動的にBacktraderによってキャンセルされる。

#### **3.2.3. トレーリングストップ処理**

* **完全にBacktraderエンジンに委任**される。  
* next()メソッド内でポジション保有中にストップ価格を監視・更新する手動ロジックは**存在しない**。これにより、「幽霊トレード」などの潜在的なバグを根本的に排除している。

## **4\. 期待される動作**

この実装により、以下のトレード動作が実現される。

1. strategy.ymlの条件に基づきエントリー注文が約定する。  
2. 約定と同時に、Backtraderが**利確注文とトレーリングストップ注文をOCOで管理開始**する。  
3. 価格が利益の出る方向に動くと、BacktraderのStopTrailロジックに従い、ストップロス価格が自動的に切り上がる（または切り下がる）。  
4. 最終的に、価格が更新されたストップロスラインに達するか、または利確ラインに達すると、ポジションが決済され、OCO連携されたもう一方の注文は自動でキャンセルされる。

# **トレード戦略のカスタマイズ方法 (v73.7)**

このシステムでは、トレードのロジックはすべてstrategy.ymlファイルで定義します。このファイルを編集することで、プログラミングの知識がなくても様々な戦略を試すことができます。

## **1\. エントリー条件の定義 (entry\_conditions)**

エントリー条件は、long（買い）とshort（売り）のそれぞれについて、満たすべき条件をリスト形式で記述します。リスト内の条件はすべて満たされる必要（AND条件）があります。

**設定例:**

entry\_conditions:  
  long: \# ロングエントリー条件  
    \# 条件1: 長期足で20EMAより上  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 20 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \# 条件2: 短期足でゴールデンクロス  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

### **1.1. 条件の基本構造**

各条件（-で始まる行）は、以下のキーで構成されます。

| パラメータ | 必須/任意 | 説明 | 設定例 |
| :---- | :---- | :---- | :---- |
| timeframe | **必須** | 条件を評価する時間足。long, medium, shortのいずれかを指定。 | "long" |
| type | 任意 | 条件の種類をcrossoverまたはcrossunderにしたい場合に指定。 | "crossover" |
| indicator | typeがない場合**必須** | **比較条件**で使用するインジケーターを定義します。 | {...} |
| compare | typeがない場合**必須** | **比較条件**の比較演算子。 | "\>" |
| target | typeがない場合**必須** | **比較条件**の比較対象。 | {...} |
| indicator1 indicator2 | typeがある場合**必須** | **クロス条件**で使用する2つのインジケーター。 | {...} |

### **1.2. indicator / indicator1 / indicator2 の詳細**

インジケーターを定義するブロックです。

| キー | 必須/任意 | 説明 | 設定例 |
| :---- | :---- | :---- | :---- |
| name | **必須** | インジケーター名。backtrader準拠。 | "ema", "sma", "rsi" |
| params | 任意 | インジケーターのパラメータ。 | { "period": 14 } |

**Note:** backtraderでサポートされているインジケーター（sma, ema, rsi, macd, stochasticなど）がnameとして利用可能です。

### **1.3. compare の種類**

比較条件で使用する演算子です。

| 値 | 説明 |
| :---- | :---- |
| \> | 左辺（indicator）が右辺（target）より大きい |
| \< | 左辺が右辺より小さい |
| between | 左辺が右辺の範囲内にある |

### **1.4. target の詳細**

インジケーターの比較対象を定義するブロックです。

| キー | 必須/任意 | 説明 | 設定例 |
| :---- | :---- | :---- | :---- |
| type | **必須** | 比較対象の種別。 | "data" (ローソク足) or "values" (固定値) |
| value | **必須** | typeに応じた具体的な値。 | "close", \[30, 70\] |

compareがbetweenの場合、valueには必ず数値を2つ指定します (例: \[30, 70\])。  
compareが\>や\<の場合、valueには数値を1つ指定します (例: \[70\])。

## **2\. イグジット条件の定義 (exit\_conditions)**

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

### **主要パラメータ解説**

* **type**:  
  * "atr\_multiple": エントリー時のATRに基づいて、固定の損益幅を設定します。  
  * "atr\_stoptrail": エントリー時のATRに基づいて初期ストップロスを設定し、その後は価格に追従（トレール）します。  
* **timeframe**: ATR計算に使用する時間足。  
* **params**:  
  * period: ATRの計算期間。  
  * multiplier: ATRの値を何倍するかを指定。

## **3\. ポジションサイジングの定義 (sizing)**

1トレードあたりのリスクに基づいて、ポジションサイズ（取引数量）を自動で計算します。**このセクションは現在、完全に機能します。**

**設定例:**

sizing:  
  \# 1トレードあたりのリスクを総資金の1%に設定  
  risk\_per\_trade: 0.01  
  \# 1トレードあたりの最大投資額を1000万円に制限  
  max\_investment\_per\_trade: 10000000

## **4\. カスタマイズの手順**

1. strategy.yml ファイルをテキストエディタで開きます。  
2. entry\_conditions, exit\_conditions, sizing セクションに、試したいルールを記述します。  
3. ファイルを保存します。  
4. ターミナルで python run\_backtrader.py を実行し、変更した戦略でバックテストを行います。  
5. python app.py を実行し、ブラウザで分析結果を確認します。

このプロセスを繰り返すことで、コードを一切触らずに、様々な戦略の有効性を高速に検証することが可能です。

# **エントリー戦略アイデア集**

## **はじめに**

このドキュメントは、**長期(long)、中期(medium)、短期(short)の3つの時間軸をすべて利用**し、様々な市場の状況に対応するための30パターンのエントリー戦略アイデア集です。

* **長期 (long):** 相場の大きな方向性（トレンドの有無、方向）を定義します。  
* **中期 (medium):** 長期トレンド内での調整（押し目・戻り）や、レンジ相場での反転ポイントを捉えます。  
* **短期 (short):** 具体的なエントリーの引き金（トリガー）となります。

これらの設定例をベースに、パラメータを最適化してご自身の戦略を構築してください。

## **カテゴリー1: トレンドフォロー戦略 (Trend Following)**

大きなトレンドに乗り、順張りで利益を狙う最も基本的な戦略群です。

**1\. SMA \+ RSI \+ EMAクロス (基本形)**

* **ロジック:** 長期SMAで上昇トレンドを確認し、中期RSIで押し目を測り、短期EMAのゴールデンクロスでエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 75 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 50 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 75 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 50 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

**2\. EMA \+ MACD \+ Stochastic**

* **ロジック:** 長期EMAでトレンド方向を定義。中期のMACDが0以上（上昇トレンド）で、短期Stochasticが売られすぎ圏からの反発を狙う。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 100 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\>", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 30 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 100 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\<", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 70 } }

**3\. ADX \+ Bollinger Bands \+ RSI**

* **ロジック:** 長期ADXでトレンドの強さを確認。中期で価格がボリンジャーバンドのミドルバンド（SMA）より上で推移し、短期RSIの押し目でエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "medium", indicator: { name: "bollinger", params: { period: 20, devfactor: 2.0 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 40 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "medium", indicator: { name: "bollinger", params: { period: 20, devfactor: 2.0 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 60 } }

**4\. Ichimoku(Proxy) \+ VWAP \+ EMAクロス**

* **ロジック:** 長期EMAを雲と見なしトレンドを判断。中期VWAPで当日の勢いを測り、短期EMAクロスでエントリー。日中取引向け。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 200 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 5 } }, indicator2: { name: "ema", params: { period: 20 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 200 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 5 } }, indicator2: { name: "ema", params: { period: 20 } } }

**5\. SMAデュアル \+ MACD \+ EMA**

* **ロジック:** 2本の長期SMAで強いトレンドを定義。中期MACDでトレンドの継続を確認し、短期で価格がEMAを上抜いたらエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 50 } }, compare: "\<", target: { type: "indicator", indicator: { name: "sma", params: { period: 150 } } } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\>", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "data", params: { value: "close" } }, indicator2: { name: "ema", params: { period: 10 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 50 } }, compare: "\>", target: { type: "indicator", indicator: { name: "sma", params: { period: 150 } } } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\<", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "data", params: { value: "close" } }, indicator2: { name: "ema", params: { period: 10 } } }

**6\. EMA \+ ADX \+ MACD**

* **ロジック:** 長期EMAでトレンド方向を、中期ADXでその強さを確認。短期MACDのゼロライン越えをエントリーシグナルとする。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 100 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "short", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\>", target: { type: "values", value: 0 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 100 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "short", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\<", target: { type: "values", value: 0 } }

**7\. SMA \+ Stochastic \+ EMAクロス**

* **ロジック:** 長期SMAでトレンドを確認後、中期Stochasticで売られすぎの押し目を待ち、短期EMAクロスでトレンドへの再復帰を捉える。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 75 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 20, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 30 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 75 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 20, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 70 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

**8\. ADX \+ RSI \+ VWAP**

* **ロジック:** 長期ADXでトレンド相場であることを確認。中期RSIで押し目を測り、短期で価格がVWAPを上抜くことで当日の勢いを確信する。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 50 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "data", params: { value: "close" } }, indicator2: { name: "vwap", params: {} } }  
  short:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 50 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "data", params: { value: "close" } }, indicator2: { name: "vwap", params: {} } }

**9\. Ichimoku(Proxy) \+ Bollinger \+ EMAクロス**

* **ロジック:** 長期EMAを雲の代わりとして長期トレンドを確認。中期で価格がBBミドルバンドより上にあり、短期EMAクロスでエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 200 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "bollinger", params: { period: 20, devfactor: 2.0 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 9 } }, indicator2: { name: "ema", params: { period: 26 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 200 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "bollinger", params: { period: 20, devfactor: 2.0 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 9 } }, indicator2: { name: "ema", params: { period: 26 } } }

**10\. EMA \+ MACD \+ RSI**

* **ロジック:** 長期EMAでトレンドを、中期MACDで勢いを判断。短期RSIが売られ過ぎゾーンからの回復を見せた時にエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 100 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\>", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 40 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 100 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\<", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 60 } }

## **カテゴリー2: 平均回帰戦略 (Mean Reversion)**

相場の「行き過ぎ」からの反転を狙う逆張り戦略です。

**11\. ADX(低) \+ Bollinger Bands \+ RSI**

* **ロジック:** 長期ADXでレンジ相場を確認。中期でボリンジャーバンド±2σにタッチし、短期RSIが行き過ぎを示す。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "bollinger", params: { period: 20, devfactor: 2.0 } }, compare: "\>", target: { type: "data", value: "low" } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "bollinger", params: { period: 20, devfactor: 2.0 } }, compare: "\<", target: { type: "data", value: "high" } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 80 } }

**12\. 長期Bollinger \+ 中期Stochastic \+ 短期RSI**

* **ロジック:** 長期ボリンジャーバンドで大きな反転ゾーンを特定。中期Stochastic、短期RSIで二重の行き過ぎを確認。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "bollinger", params: { period: 50, devfactor: 2.5 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 7 } }, compare: "\<", target: { type: "values", value: 30 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "bollinger", params: { period: 50, devfactor: 2.5 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 80 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 7 } }, compare: "\>", target: { type: "values", value: 70 } }

**13\. RSI \+ RSI \+ RSI**

* **ロジック:** 全時間足でRSIの売られすぎ/買われすぎを確認し、非常に強い反転の可能性を捉える。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 40 } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 30 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 60 } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 70 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 80 } }

**14\. Stochastic \+ Stochastic \+ EMAクロス**

* **ロジック:** 長期・中期Stochasticで相場の過熱感を確認し、短期EMAの逆方向クロスで反転エントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "stochastic", params: { period: 20, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 5 } }, indicator2: { name: "ema", params: { period: 10 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "stochastic", params: { period: 20, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 80 } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 80 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 5 } }, indicator2: { name: "ema", params: { period: 10 } } }

**15\. ADX(低) \+ VWAP \+ Stochastic**

* **ロジック:** 長期的なレンジ相場の中、当日の価格がVWAPから大きく乖離し、短期Stochasticが行き過ぎを示した時に逆張り。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 20 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 80 } }

## **カテゴリー3: ボラティリティブレイクアウト戦略 (Volatility Breakout)**

静かな相場から動き出す瞬間を捉える戦略です。

**16\. ATR(低) \+ ATR(低) \+ EMAクロス**

* **ロジック:** 長期・中期でボラティリティの低下（ATRの低水準）を確認。短期のクロスで動き出しを捉える。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 10.0 } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 5.0 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 5 } }, indicator2: { name: "ema", params: { period: 20 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 10.0 } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 5.0 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 5 } }, indicator2: { name: "ema", params: { period: 20 } } }

**17\. ATR(低) \+ SMA \+ Price Break**

* **ロジック:** 中期ATRで相場の収縮を確認。長期SMAでブレイク方向を予測し、短期価格が高速EMAを上抜くことでエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 50 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 20 } }, compare: "\<", target: { type: "values", value: 7.0 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "data", params: { value: "close" } }, indicator2: { name: "ema", params: { period: 10 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 50 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 20 } }, compare: "\<", target: { type: "values", value: 7.0 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "data", params: { value: "close" } }, indicator2: { name: "ema", params: { period: 10 } } }

**18\. ADX(低) \+ ADX(低) \+ MACDゼロクロス**

* **ロジック:** 長期・中期でADXが低水準にあり、エネルギーを溜めている状態を確認。短期MACDのゼロクロスをブレイクのサインとする。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, indicator2: { name: "values", value: 0 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, indicator2: { name: "values", value: 0 } }

**19\. ATR(高) \+ ATR(高) \+ EMAクロス**

* **ロジック:** 逆に、すでにボラティリティが高い相場での順張り戦略。長期・中期共にATRが高いことを確認し、短期の押し目からの再上昇を狙う。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 20.0 } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 10.0 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 20.0 } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 10.0 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

**20\. Ichimoku(Proxy)収縮 \+ ADX \+ EMAクロス**

* **ロジック:** 長期ATRの低下を雲の収縮と見なし、中期ADXの上昇でブレイクの予兆を捉え、短期EMAクロスでエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 50 } }, compare: "\<", target: { type: "values", value: 15.0 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 9 } }, indicator2: { name: "ema", params: { period: 26 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 50 } }, compare: "\<", target: { type: "values", value: 15.0 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 9 } }, indicator2: { name: "ema", params: { period: 26 } } }

## **カテゴリー4: 複合戦略 (Hybrid Strategies)**

異なるタイプのロジックを組み合わせた高度な戦略です。

**21\. トレンド \+ ボラティリティフィルター**

* **ロジック:** 基本のトレンドフォロー戦略に、長期ATRフィルターを追加。市場が動いている時のみエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 75 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 15.0 } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 50 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 75 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "long", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 15.0 } }  
    \- { timeframe: "medium", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 50 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

**22\. トレンド内カウンタートレード**

* **ロジック:** 長期トレンド（SMA）を確認し、中期のStochasticで行き過ぎの反動を狙い、短期RSIでエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 100 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 20, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 7 } }, compare: "\>", target: { type: "values", value: 50 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 100 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 20, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 80 } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 7 } }, compare: "\<", target: { type: "values", value: 50 } }

**23\. ADX(トレンド) \+ ADX(レンジ) \+ EMAクロス**

* **ロジック:** 長期でトレンドがある(高ADX)中で、中期で調整局面(低ADX)に入った後の、短期EMAクロスによる再ブレイクを狙う。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 20 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

**24\. VWAP \+ SMA \+ RSI**

* **ロジック:** 長期SMAで大局観を、中期VWAPで当日の勢いを判断。短期RSIで精密な押し目買いのタイミングを計る。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 50 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 40 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 50 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 60 } }

**25\. MACD \+ Stochastic \+ RSI**

* **ロジック:** 3つのオシレーターを各時間足で役割分担。長期MACDで大きな流れ、中期Stochasticで押し目、短期RSIでエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\>", target: { type: "values", value: 0 } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 30 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "rsi", params: { period: 7 } }, indicator2: { name: "values", value: 30 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\<", target: { type: "values", value: 0 } }  
    \- { timeframe: "medium", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 70 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "rsi", params: { period: 7 } }, indicator2: { name: "values", value: 70 } }

**26\. Bollinger \+ EMA \+ MACD**

* **ロジック:** 長期BBミドルバンドでトレンド方向を、中期EMAでサポートを確認。短期MACDのゼロクロスでエントリー。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "bollinger", params: { period: 50, devfactor: 2.0 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "ema", params: { period: 50 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, indicator2: { name: "values", value: 0 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "bollinger", params: { period: 50, devfactor: 2.0 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "ema", params: { period: 50 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, indicator2: { name: "values", value: 0 } }

**27\. SMA \+ VWAP \+ VWAP**

* **ロジック:** 長期SMAで大きなトレンド方向を決定。中期・短期ともに価格がVWAPより上にあることを確認し、強い買い（売り）圧力が継続している局面を狙う。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 100 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "vwap", params: {} }, compare: "\<", target: { type: "data", value: "close" } }  
  short:  
    \- { timeframe: "long", indicator: { name: "sma", params: { period: 100 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "vwap", params: {} }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "short", indicator: { name: "vwap", params: {} }, compare: "\>", target: { type: "data", value: "close" } }

**28\. RSI \+ ADX \+ EMAクロス**

* **ロジック:** 長期RSIで過熱感をフィルタリング（買われすぎでない）。中期ADXでトレンドの強さを確認し、短期EMAクロスで順張り。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "rsi", params: { period: 14 } }, compare: "\<", target: { type: "values", value: 70 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "short", type: "crossover", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }  
  short:  
    \- { timeframe: "long", indicator: { name: "rsi", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 30 } }  
    \- { timeframe: "medium", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 25 } }  
    \- { timeframe: "short", type: "crossunder", indicator1: { name: "ema", params: { period: 10 } }, indicator2: { name: "ema", params: { period: 25 } } }

**29\. Ichimoku(Proxy) \+ ATR \+ Stochastic**

* **ロジック:** 長期EMAを雲と見なしてトレンドを定義。中期ATRでボラティリティがあることを確認し、短期Stochasticで押し目を狙う。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 200 } }, compare: "\<", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 10.0 } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 30 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "ema", params: { period: 200 } }, compare: "\>", target: { type: "data", value: "close" } }  
    \- { timeframe: "medium", indicator: { name: "atr", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 10.0 } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 70 } }

**30\. ADX \+ MACD \+ Stochastic**

* **ロジック:** 長期ADXでトレンドの有無を確認。中期MACDでその方向性を判断。短期Stochasticで押し目/戻りのタイミングを計る。

entry\_conditions:  
  long:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\>", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\<", target: { type: "values", value: 40 } }  
  short:  
    \- { timeframe: "long", indicator: { name: "adx", params: { period: 14 } }, compare: "\>", target: { type: "values", value: 20 } }  
    \- { timeframe: "medium", indicator: { name: "macd", params: { fast\_period: 12, slow\_period: 26, signal\_period: 9 } }, compare: "\<", target: { type: "values", value: 0 } }  
    \- { timeframe: "short", indicator: { name: "stochastic", params: { period: 14, period\_dfast: 3, period\_dslow: 3 } }, compare: "\>", target: { type: "values", value: 60 } }  
