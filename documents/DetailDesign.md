# **株自動トレードシステム 詳細設計書 (v7.2)**

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
   * Webブラウザで http://127.0.0.1:5001 を開く。

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
  * trading\_mode: long\_enabledとshort\_enabledで、ロング戦略とショート戦略の有効/無効を個別に切り替える。  
  * timeframes: 長期・中期・短期の時間足と圧縮率を定義。  
  * entry\_conditions: **エントリー戦略のコアロジックを定義する。**  
    * long/shortの各セクションに、満たすべき条件をリスト形式で記述する（AND条件）。  
    * 各条件は、timeframe, indicator, compare, target, typeなどのキーを組み合わせて定義する。  
  * exit\_conditions: ATRに基づいた**損切り・利確ルール**を定義する。stop\_lossでは固定損切り(atr\_multiple)とトレーリング損切り(atr\_trailing\_stop)を選択可能。  
  * sizing: 1トレードあたりのリスク許容度（資金に対する割合）に基づいた**ポジションサイズ計算ルール**を定義する。  
  * indicators: Web UIで表示する各テクニカル指標の**表示上のデフォルト値**を定義する。**バックテストのロジックには直接影響しない。**

### **4.4. email\_config.yml**

* **役割**: メール送信に関する機密情報（ID、パスワード等）をコード本体から分離し、セキュリティを確保する。  
* **主要な内容**:  
  * ENABLED: メール通知機能の有効/無効を切り替えるフラグ。  
  * SMTP\_SERVER, SMTP\_PORT: 送信に使用するメールサーバーの情報。  
  * SMTP\_USER, SMTP\_PASSWORD: 認証情報。  
  * RECIPIENT\_EMAIL: 通知を受け取るメールアドレス。

### **4.5. logger\_setup.py**

* **役割**: Python標準のloggingモジュールを設定し、一元的なログ管理機能を提供する。  
* **主要な内容**: setup\_logging()  
  * 実行時のタイムスタンプに基づき、log/backtest\_YYYY-MM-DD-HHMMSS.logというユニークなファイル名を生成する。  
  * ログのフォーマットを「時間 \- レベル \- モジュール名 \- メッセージ」に統一する。  
  * ログの出力先を、コンソール（画面）と上記ログファイルの両方に設定する。

### **4.6. notifier.py**

* **役割**: メール通知機能の実装。  
* **主要な内容**: send\_email(subject, body)  
  * email\_config.ymlを読み込み、通知が有効になっているか確認する。  
  * 有効な場合、Python標準のsmtplibを使い、設定情報に基づいてメールを作成し送信する。

### **4.7. btrader\_strategy.py**

* **役割**: strategy.ymlを動的に解釈する汎用的な戦略実行エンジンとして機能する。  
* **主要な内容**:  
  * \_\_init\_\_(self):  
    * strategy.ymlから渡されたパラメータを読み込む。  
    * entry\_conditionsとexit\_conditionsを走査し、戦略で必要となる全てのベースインジケーター（EMA, RSI, ATRなど）と、それらを利用するCrossOverインジケーターを**事前に一度だけ**インスタンス化し、辞書に保持する。  
  * \_evaluate\_condition(self, cond):  
    * YAMLに定義された単一の条件（例: ema \> closeやema1 crossover ema2）を評価するヘルパー関数。  
  * next(self):  
    * 毎ローソク足ごとに呼び出されるメインロジック。  
    * **ポジションがない場合**: \_check\_all\_conditions()を呼び出し、エントリー条件を評価。条件が満たされた場合、sizingとexit\_conditionsに基づき**リスク計算、ポジションサイズ、損切り/利確価格を決定**し、エントリー注文 (self.buy()/self.sell()) を発注する。  
    * **ポジションがある場合**: stop\_lossがatr\_trailing\_stopに設定されていれば、ローソク足ごとに損切り価格を更新するロジックを実行する。  
  * notify\_order(self, order):  
    * 注文状態を監視し、ログを出力する。  
    * エントリー注文が約定した場合、**正確な約定数量をself.executed\_sizeに保存**し、定義されていれば**損切り注文と利確注文を続いて発注**する。  
    * 損切りまたは利確注文が約定した場合、もう一方の未約定注文をキャンセルする。  
  * notify\_trade(self, trade):  
    * トレード完了（クローズ）を監視し、ログを出力する。

### **4.8. report\_generator.py**

* **役割**: 複数のバックテスト結果を集約し、人間が読みやすい形式の総合サマリーレポートを生成する。  
* **主要な内容**: generate\_report(...)  
  * 全銘柄のraw\_statsリストとstrategy.ymlのパラメータを受け取る。  
  * 純利益、勝率、プロフィットファクターなどのパフォーマンス指標を**全体で合算・再計算**する。  
  * 計算結果に基づき、「総損益」「勝率」などに対する定性的な評価コメントを生成する。  
  * strategy.ymlからエントリー/イグジットロジックの説明文を動的に生成する。  
  * これら全ての情報を整形し、最終的なpandas.DataFrameとして返す。

### **4.9. run\_backtrader.py**

* **役割**: バックテスト全体の実行を管理し、レポートファイル（CSV）を出力する。  
* **主要な内容**:  
  * TradeList(bt.Analyzer): 取引履歴を詳細に記録するためのカスタムアナライザー。  
    * スリッページを考慮した正確な決済価格を、最終損益から**逆算して**記録する。  
    * 約定数量は戦略クラスのexecuted\_sizeから取得する。  
  * run\_backtest\_for\_symbol(...):  
    * Cerebroエンジンを初期化し、btrader\_strategy.DynamicStrategyにstrategy.ymlから読み込んだパラメータを渡して追加する。  
    * cerebro.run()でバックテストを実行し、アナライザーから数値結果と取引リストを抽出して返す。  
  * main():  
    * strategy.ymlを読み込む。  
    * dataディレクトリ内の全CSVファイルに対してrun\_backtest\_for\_symbolをループ実行し、結果をリストに集約する。  
    * report\_generatorを呼び出して総合サマリーレポートを作成・保存する。  
    * 集計したデータから、銘柄別詳細レポートと統合取引履歴レポートをそれぞれ作成・保存する。

### **4.10. app.py (Webアプリケーションサーバー)**

* **役割**: Flaskサーバーを起動し、フロントエンドとバックエンドの橋渡しを行う。  
* **主要なエンドポイント**:  
  * @app.route('/'): メインページ (index.html) を描画する。  
  * @app.route('/get\_chart\_data'):  
    * ブラウザからの非同期リクエストを受け付けるAPI。  
    * リクエストのクエリパラメータ（銘柄、時間足、全インジケーターのパラメータ）を取得する。  
    * 取得したパラメータを chart\_generator.generate\_chart\_json() に渡し、チャートのJSONデータを生成させる。  
    * チャートデータと取引履歴データをまとめてJSON形式でブラウザに返す。  
* **起動処理**:  
  * サーバー起動時に chart\_generator.load\_data() を一度だけ呼び出し、価格データと取引履歴をメモリにキャッシュする。

### **4.11. templates/index.html (フロントエンドUI)**

* **役割**: ユーザーインターフェースの構造を定義し、チャートの動的更新ロジックを実装する。  
* **主要なコンポーネント**:  
  * **コントロールパネル**: 銘柄と時間足の選択、および各インジケーターのパラメータ変更フォームを配置。  
  * **チャート表示領域**: Plotlyのグラフが描画される \<div\> タグ。  
  * **取引履歴テーブル**: チャートの下部に配置。  
* **主要なJavaScriptロジック**:  
  * updateChart(): コントロールパネルの値をAPIに送信し、返されたJSONでチャートとテーブルを更新する。  
  * highlightTradeOnChart(): テーブル行のクリックに連動し、チャート上の取引期間をハイライトする。

### **4.12. chart\_generator.py (チャート生成モジュール)**

* **役割**: app.pyから呼び出されるライブラリとして、Plotlyのグラフオブジェクトを生成する。  
* **主要な関数**:  
  * load\_data(): アプリケーション起動時に一度だけ呼ばれ、必要なCSVデータをキャッシュに読み込む。  
  * generate\_chart\_json(...):  
    * キャッシュから価格データを取得。  
    * 受け取ったパラメータに基づき、各種テクニカル指標を動的に計算。  
    * make\_subplotsで価格チャートと各指標用のサブプロットを動的に作成。  
    * go.Candlestick, go.Bar, go.Scatterなどを使い、フィギュアを構築する。  
    * フィギュアオブジェクトをJSON形式の文字列に変換して返す。  
  * get\_trades\_for\_symbol(symbol): キャッシュから指定された銘柄の取引履歴データを抽出して返す。