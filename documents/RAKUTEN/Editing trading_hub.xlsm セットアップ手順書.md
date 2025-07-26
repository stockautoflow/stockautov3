## **`trading_hub.xlsm` セットアップ手順書**

この手順書は、`generate_workbook.py`で生成された`trading_hub.xlsm`ファイルに、手動で必要な設定を行い、リアルタイムトレードシステムとの連携を完了させるためのものです。

### 0. 事前準備

以下の準備が完了していることを確認してください。

  * PCにマーケットスピード II (MS2) がインストールされていること。
  * MS2の「環境設定」で「API連携」が有効になっていること。
  * `generate_workbook.py`を実行し、`external`ディレクトリ内に`trading_hub.xlsm`が作成されていること。

-----

### 1. VBAマクロの組み込み

Pythonからの注文指示を処理するためのVBAコードをExcelファイルに組み込みます。

1.  **ファイルを開き、コンテンツを有効化**

      * `external/trading_hub.xlsm`をExcelで開きます。
      * セキュリティ警告が表示された場合は、「**コンテンツの有効化**」ボタンをクリックしてマクロを有効にします。

2.  **VBAエディタを開く**

      * `Alt` + `F11`キーを押して、VBAエディタ（VBE）を開きます。

3.  **コードウィンドウを開く**

      * VBAエディタの左側にある「プロジェクトエクスプローラー」から、`VBAProject (trading_hub.xlsm)`を探します。
      * `Microsoft Excel Objects`フォルダを展開し、`Sheet2 (注文)`をダブルクリックします。

4.  **コードの貼り付け**

      * 右側に表示された白紙のコードウィンドウに、以下のVBAコードを**全てコピーして貼り付け**ます。

    <!-- end list -->

    ```vb
    '================================================================
    ' 注文シートのコードモジュール
    '================================================================
    Private Sub Worksheet_Change(ByVal Target As Range)
        
        ' 監視対象セル(E2)以外が変更された場合は何もしない
        If Intersect(Target, Me.Range("E2")) Is Nothing Then
            Exit Sub
        End If

        ' --- 変数定義 ---
        Dim symbol As String
        Dim side As String
        Dim quantity As Long
        Dim orderType As String
        Dim price As Double
        Dim result As Variant
        
        ' --- 実行前処理 ---
        On Error GoTo ErrorHandler
        Me.Range("C2").Value = "実行中..."
        Me.Range("C3:C4").ClearContents ' 前回の結果をクリア

        ' --- 1. 入力値の取得 ---
        symbol = CStr(Me.Range("B2").Value)
        side = CStr(Me.Range("B3").Value)
        quantity = CLng(Me.Range("B4").Value)
        orderType = CStr(Me.Range("B5").Value)
        price = CDbl(Me.Range("B6").Value)

        ' --- 2. MS2注文関数の呼び出し (※注意: 関数名や引数はMS2の仕様に合わせてください) ---
        ' result = MarketSpeed2.System.NewOrder(symbol, side, quantity, orderType, price)

        ' ↓↓↓【ダミー処理】MS2に接続できない環境でのテスト用。実際は上記を有効化する。↓↓↓
        Dim dummyResult(1 To 2) As Variant
        If IsNumeric(symbol) And quantity > 0 Then
            dummyResult(1) = "Success"
            dummyResult(2) = "ORDER_" & CStr(Int(Rnd * 10000))
        Else
            dummyResult(1) = "Error"
            dummyResult(2) = "無効なパラメータです。"
        End If
        ' ↑↑↑【ダミー処理ここまで】↑↑↑

        ' --- 3. 結果の書き込み ---
        ' If result(1) = "Success" Then ' MS2からの戻り値が成功の場合
        If dummyResult(1) = "Success" Then ' ダミー処理の場合
            Me.Range("C2").Value = "成功"
            Me.Range("C3").Value = dummyResult(2) ' 注文ID
        Else
            Me.Range("C2").Value = "エラー"
            Me.Range("C4").Value = dummyResult(2) ' エラーメッセージ
        End If

    GoTo Finally

    ErrorHandler:
        ' --- エラー処理 ---
        Me.Range("C2").Value = "VBAエラー"
        Me.Range("C4").Value = Err.Description

    Finally:
        ' --- 4. 完了通知 (エラー発生時も必ず実行) ---
        Me.Range("E3").Value = Me.Range("E2").Value
        
    End Sub
    ```

5.  **保存して閉じる**

      * `Ctrl` + `S`キーで保存し、VBAエディタを閉じます。

-----

### 2. 監視銘柄の設定

Pythonプログラムがデータを取得したい銘柄を`リアルタイムデータ`シートに設定します。

1.  `trading_hub.xlsm`の`リアルタイムデータ`シートを開きます。

2.  **A列**（銘柄コード）に、監視したい銘柄のコードを`A2`セルから下に向かって入力します。（サンプルで入力されている銘柄は消しても構いません）

3.  `B2`セルから`F2`セルまでを選択し、セルの右下に表示される小さい四角（フィルハンドル）をドラッグして、入力した銘柄コードの行まで数式をコピーします。

-----

### 3. 動作確認

設定が正しく完了したかを確認します。

1.  **MS2を起動し、ログインします。**
2.  `trading_hub.xlsm`を開き、`リアルタイムデータ`シートに設定した銘柄の株価が**B列以降にリアルタイムで表示**されることを確認します。
      * `#N/A`などのエラーが表示される場合は、MS2との連携がうまくいっていません。MS2の再起動やAPI連携設定を再確認してください。
3.  VBAマクロのテスト手順書（TC-01）に従って、`注文`シートで手動テストを行い、注文処理が正常に動作することを確認します。

以上でセットアップは完了です。
この状態で`trading_hub.xlsm`とMS2を起動したまま、Pythonのリアルタイムトレードシステムを実行してください。