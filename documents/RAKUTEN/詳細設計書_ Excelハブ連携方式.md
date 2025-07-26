承知いたしました。  
Excelハブ連携方式の詳細設計書をMarkdown形式で再掲します。

---

## **詳細設計書: Excelハブ連携方式**

### **1\. 概要**

本設計書は、マーケットスピード II (MS2) との直接的なAPI連携の代わりに、**Excelワークブックを通信ハブ**として利用するシステムアーキテクチャを定義します。PythonプログラムとMS2は、このExcelワークブックを介してデータ取得と注文執行を非同期で行います。

---

### **2\. 設計対象コンポーネント**

#### **2.1. Excel側コンポーネント**

| コンポーネント | タイプ | 概要 |
| :---- | :---- | :---- |
| **trading\_hub.xlsm** | Excelワークブック | データ連携と注文執行のハブとなるマクロ有効ワークブック。 |
| **リアルタイムデータ** | ワークシート | MS2のRSS機能を利用してリアルタイムの市場データ（株価、出来高など）を表示します。 |
| **注文** | ワークシート | Pythonからの注文指示を受け取り、VBAからの実行結果を返すインターフェース。 |
| **OrderModule** | VBAモジュール | 「注文」シートの変更を検知し、MS2の注文機能を呼び出すマクロを格納します。 |

#### **2.2. Python側コンポーネント**

| コンポーネント | タイプ | 概要 |
| :---- | :---- | :---- |
| **excel\_bridge.py** | 新規作成 | Excelワークブックとのリアルタイム通信（読み書き）を担う中核モジュール。 |
| **rakuten\_data.py** | 新規作成 | ExcelBridgeを介して取得したデータをbacktraderのデータフィード形式に変換します。 |
| **rakuten\_broker.py** | 新規作成 | backtraderの注文指示をExcelBridge経由でExcelに書き込みます。 |
| **run\_realtrade.py** | 修正 | ExcelBridgeのインスタンスを生成し、RakutenDataとRakutenBrokerに渡すよう修正します。 |

---

### **3\. Excelワークブック設計 (trading\_hub.xlsm)**

#### **3.1. ワークシート: リアルタイムデータ**

このシートはPythonへの**データ提供**を担当します。

|  | A | B | C | D | E |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **1** | **銘柄コード** | **現在値** | **始値** | **高値** | **安値** |
| **2** | 9984 | \=MS2.RSS(A2,"現在値") | \=MS2.RSS(A2,"始値") | \=MS2.RSS(A2,"高値") | \=MS2.RSS(A2,"安値") |
| **3** | 7203 | \=MS2.RSS(A3,"現在値") | \=MS2.RSS(A3,"始値") | \=MS2.RSS(A3,"高値") | \=MS2.RSS(A3,"安値") |
| ... | ... | ... | ... | ... | ... |
| **10** | **項目** | **値** |  |  |  |
| **11** | 買付余力 | \=MS2.ACCOUNT(...) |  |  |  |

* **A列:** Pythonから監視対象の銘柄コードが入力されます。  
* **B列以降:** MS2のRSS関数を埋め込み、リアルタイムで値が更新されます。  
* **口座情報:** 買付余力などもRSS関数で取得し、特定のセル（例: B11）に表示しておきます。

#### **3.2. ワークシート: 注文**

このシートはPythonとVBA間の**双方向通信**による注文執行インターフェースとなります。

|  | A | B (Python → VBA) | C (VBA → Python) | D (同期用) |
| :---- | :---- | :---- | :---- | :---- |
| **1** | **項目** | **入力値** | **実行結果** | **トリガー** |
| **2** | 銘柄コード | *(例: 9984\)* | 処理ステータス | 実行ID (Python) |
| **3** | 売買区分 | *(例: BUY)* | 注文ID | 完了ID (VBA) |
| **4** | 数量 | *(例: 100\)* | メッセージ |  |
| **5** | 注文種別 | *(例: MARKET)* |  |  |
| **6** | 指値価格 |  |  |  |

* **B列 (入力):** Pythonが注文内容を書き込みます。  
* **C列 (出力):** VBAマクロが実行結果を書き込みます。  
* **D2 (実行ID):** Pythonが注文のたびにインクリメントする数値（例: 1, 2, 3...）。VBAマクロはこのセルの変更を検知して起動します。  
* **D3 (完了ID):** VBAマクロが処理完了後、D2の値をここにコピーします。PythonはD3がD2と同じ値になるのを待つことで処理完了を検知します。

#### **3.3. VBAモジュール: OrderModule**

注文シートに紐づくVBAマクロ。

VB.Net

' 注文シートのWorksheet\_Changeイベント  
Private Sub Worksheet\_Change(ByVal Target As Range)  
    ' D2セル (実行ID) の変更のみを監視  
    If Not Intersect(Target, Me.Range("D2")) Is Nothing Then  
        ' 1\. 注文情報をB列から読み取る  
        Dim symbol As String, side As String, qty As Long, ...  
        symbol \= Me.Range("B2").Value  
        ' ...

        ' 2\. 処理ステータスを「実行中」に更新  
        Me.Range("C2").Value \= "PENDING"

        ' 3\. MS2の注文関数を呼び出し  
        Dim result As Variant  
        result \= MarketSpeed2.System.NewOrder(symbol, side, qty, ...)

        ' 4\. 実行結果をC列に書き込む  
        If result("Success") Then  
            Me.Range("C2").Value \= "SUCCESS"  
            Me.Range("C3").Value \= result("OrderID")  
        Else  
            Me.Range("C2").Value \= "ERROR"  
            Me.Range("C4").Value \= result("Message")  
        End If

        ' 5\. 完了IDを更新してPythonに通知  
        Me.Range("D3").Value \= Me.Range("D2").Value  
    End If  
End Sub

---

### **4\. Pythonコンポーネント設計**

#### **4.1. excel\_bridge.py (ExcelBridge クラス)**

Python

import xlwings as xw  
import threading  
import time

class ExcelBridge:  
    def \_\_init\_\_(self, workbook\_path):  
        \# xlwingsでExcelに接続し、各シートへのハンドルを保持  
        self.book \= xw.Book(workbook\_path)  
        self.data\_sheet \= self.book.sheets\['リアルタイムデータ'\]  
        self.order\_sheet \= self.book.sheets\['注文'\]  
        self.order\_lock \= threading.Lock() \# 注文処理の競合を防ぐ  
        self.latest\_data \= {} \# 最新データをキャッシュする辞書

    def start\_data\_listener(self):  
        \# データシートを監視するバックグラウンドスレッドを開始  
        self.data\_thread \= threading.Thread(target=self.\_data\_loop, daemon=True)  
        self.data\_thread.start()

    def \_data\_loop(self):  
        \# リアルタイムデータシートから値を読み取り、キャッシュを更新し続ける  
        while True:  
            \# (例) A2:E3 の範囲を一括で読み取る  
            range\_values \= self.data\_sheet.range('A2:E3').options(ndim=2).value  
            for row in range\_values:  
                symbol \= row\[0\]  
                self.latest\_data\[symbol\] \= {'price': row\[1\], 'open': row\[2\], ...}  
            time.sleep(0.5) \# 読み取り間隔

    def get\_latest\_price(self, symbol):  
        return self.latest\_data.get(symbol, {}).get('price')

    def get\_cash(self):  
        \# 買付余力セルから値を取得  
        return self.data\_sheet.range('B11').value

    def place\_order(self, symbol, side, qty):  
        with self.order\_lock:  
            \# 1\. 注文内容をExcelに書き込み  
            self.order\_sheet.range('B2').value \= \[symbol, side, qty, 'MARKET', ''\]

            \# 2\. 実行IDをインクリメントしてVBAをトリガー  
            execute\_id \= self.order\_sheet.range('D2').value \+ 1  
            self.order\_sheet.range('D2').value \= execute\_id

            \# 3\. VBAの処理完了をポーリングで待機 (タイムアウト付き)  
            start\_time \= time.time()  
            while time.time() \- start\_time \< 10: \# 10秒でタイムアウト  
                if self.order\_sheet.range('D3').value \== execute\_id:  
                    \# 4\. 結果を読み取って返す  
                    status \= self.order\_sheet.range('C2').value  
                    order\_id \= self.order\_sheet.range('C3').value  
                    return {"status": status, "order\_id": order\_id}  
                time.sleep(0.2)  
              
            return {"status": "TIMEOUT"}

#### **4.2. rakuten\_broker.py & rakuten\_data.py**

これらのクラスはExcelBridgeを利用する薄いラッパーとして機能します。

* **RakutenBroker:**  
  * \_\_init\_\_でExcelBridgeのインスタンスを受け取ります。  
  * buy, sellメソッドは、内部でself.bridge.place\_order(...)を呼び出します。  
  * getcashメソッドはself.bridge.get\_cash()を返します。  
* **RakutenData:**  
  * \_\_init\_\_でExcelBridgeのインスタンスを受け取ります。  
  * \_loadメソッドは、self.bridge.get\_latest\_price(self.symbol)を呼び出してデータを取得し、self.linesを更新します。

---

### **5\. 実行フローの統合**

run\_realtrade.pyで、以下のようにExcelBridgeを初期化し、各コンポーネントに渡します。

Python

\# run\_realtrade.py (抜粋)

from .excel\_bridge import ExcelBridge  
\# ...

def main():  
    \# ...  
    \# ExcelBridgeのインスタンスを一度だけ生成  
    bridge \= ExcelBridge(workbook\_path="C:/path/to/trading\_hub.xlsm")  
    bridge.start\_data\_listener()

    \# Cerebroのセットアップ時にbridgeを渡す  
    store \= RakutenStore(bridge=bridge)  
    broker \= RakutenBroker(bridge=bridge)  
    cerebro.setbroker(broker)  
    \# ...  
