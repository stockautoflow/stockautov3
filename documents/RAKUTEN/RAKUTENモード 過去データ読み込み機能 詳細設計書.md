はい、承知いたしました。
RAKUTENモードが起動時に過去の株価データを読み込み、インジケーターを即座に計算できるようにするための改修について、詳細設計書を作成します。

-----

## RAKUTENモード 過去データ読み込み機能 詳細設計書

### 1\. 目的

RAKUTENモードにおいて、**システムの起動時に`data`ディレクトリから過去の株価データ（CSV）を読み込む**機能を実装する。

これにより、インジケーターの計算に必要なデータが即座に供給され、これまで長時間待機しないと発生しなかった以下の問題を解決する。

  * インジケーター（特にリサンプリングで生成される中期・長期足のもの）が計算されない問題。
  * 上記に起因して、売買シグナルが一切生成されないという根本的なバグ。

### 2\. 設計方針

  * YAHOOモードやバックテストと同様に、`data`ディレクトリに配置されたCSVファイル (`<銘柄コード>_<時間>m_*.csv`) を過去データとして利用する。
  * `run_realtrade.py`内で、RAKUTENモードのデータフィードを生成する前に、対応する銘柄の**過去データCSVを`pandas.DataFrame`として読み込む**。
  * `RakutenData`クラスを改修し、初期化時に過去データのDataFrameを受け取れるようにする。
  * `RakutenData`は、まず**保持している過去データを全て供給**し、それが完了した後に**Excelからのリアルタイムデータ供給にシームレスに切り替える**。

### 3\. 修正対象と実装詳細

#### 3.1. `src/realtrade/run_realtrade.py` の修正

**対象メソッド**: `_create_cerebro_for_symbol`

RAKUTENモードの処理ブロック内で、`RakutenData`をインスタンス化する前に、CSV読み込み処理を追加します。

**修正後の処理フロー:**

```python
# if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN': のブロック内

# 1. [新規] 銘柄に対応する過去データCSVのパスを特定
short_tf_config = strategy_params['timeframes']['short']
compression = short_tf_config['compression']
search_pattern = os.path.join(config.DATA_DIR, f"{symbol}_{compression}m_*.csv")
files = glob.glob(search_pattern)

# 2. [新規] CSVファイルをDataFrameに読み込む
hist_df = pd.DataFrame() # デフォルトは空
if files:
    latest_file = max(files, key=os.path.getctime)
    try:
        hist_df = pd.read_csv(latest_file, index_col='datetime', parse_dates=True)
        logger.info(f"[{symbol}] 過去データとして '{os.path.basename(latest_file)}' を読み込みました。")
    except Exception as e:
        logger.error(f"[{symbol}] 過去データCSVの読み込みに失敗: {e}")
else:
    logger.warning(f"[{symbol}] 過去データCSVが見つかりません (パターン: {search_pattern})。リアルタイムデータのみで開始します。")

# 3. [修正] RakutenDataの初期化時に、読み込んだDataFrameを`dataname`として渡す
primary_data = RakutenData(
    dataname=hist_df, # ここで過去データを渡す
    bridge=self.bridge,
    symbol=symbol,
    timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']),
    compression=short_tf_config['compression']
)

# ... (以降の cerebro.adddata や resampledata の処理は変更なし)
```

-----

#### 3.2. `src/realtrade/rakuten/rakuten_data.py` の修正

**対象クラス**: `RakutenData`

初期化時に渡された過去データを保持し、`_load`メソッドで供給するロジックを追加します。

**主な変更点:**

1.  **`__init__`メソッドの変更**

      * 渡された`dataname`(過去データ)をインスタンス変数 `self._hist_df` に格納する。
      * 自身で空のDataFrameを生成するロジックは削除する。

2.  **`_load`メソッドの変更**

      * `_load`メソッドのロジックを以下のように変更し、過去データとリアルタイムデータを段階的に供給するようにします。

    <!-- end list -->

    ```python
    # _loadメソッドの新しいロジック

    # --- 1. 過去データの供給フェーズ ---
    if not self._hist_df.empty:
        # 過去データDFから最初の行を取得して供給
        row = self._hist_df.iloc[0]
        self._hist_df = self._hist_df.iloc[1:] # 供給した行を削除
        self._populate_lines(row) # バーの値をセット
        return True # データ供給成功

    # --- 2. リアルタイムデータの供給フェーズ ---
    # (過去データが空になった後、既存のリアルタイム処理に移行)
    if self._stopevent.is_set():
        return False

    # ... (以降、既存のExcelBridgeからのデータ取得とハートビート供給のロジック)
    ```

### 4\. 期待される効果

  * システムの起動と同時に、過去データに基づいたインジケーター（日足など長期のものを含む）が計算される。
  * 稼働開始直後から、全ての戦略条件が正しく評価され、売買シグナルの生成が可能になる。
  * RAKUTENモードとYAHOOモードの動作がより一貫性の高いものになる。