# test_excel_connection.py

import xlwings as xw
import os
import time
from datetime import datetime

# --- 設定値 ---
WORKBOOK_DIR = "external"
WORKBOOK_NAME = "trading_hub.xlsm"
TARGET_SHEET = "リアルタイムデータ"
TARGET_CELL = "B2" # 9984の現在値セル

def main():
    """
    Excelに接続し、指定セルの値をリアルタイムで読み取るテストスクリプト。
    """
    workbook_path = os.path.join(WORKBOOK_DIR, WORKBOOK_NAME)

    # 1. ファイルの存在確認
    if not os.path.exists(workbook_path):
        print(f"エラー: ファイルが見つかりません: {workbook_path}")
        return

    print(f"'{workbook_path}' への接続を試みます...")
    print("Excelでファイルを開き、MS2にログインしていることを確認してください。")
    print("スクリプトを停止するには Ctrl+C を押してください。")

    try:
        # 2. Excelワークブックに接続
        # 注意: xw.Book()はExcelが起動していない場合、Excelを起動しようとします。
        #       既に開いているファイルに接続するのが最も確実です。
        book = xw.Book(workbook_path)
        sheet = book.sheets[TARGET_SHEET]
        
        print(f"\n接続成功。シート '{TARGET_SHEET}' のセル '{TARGET_CELL}' の監視を開始します。")

        # 3. データ読み取りループ
        while True:
            # セルの値を読み取り
            value = sheet.range(TARGET_CELL).value
            
            # 現在時刻と値を表示
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"{timestamp} - 読み取り成功: {TARGET_CELL}の値 = {value}")
            
            # 1秒待機
            time.sleep(1)

    except Exception as e:
        print(f"\nエラーが発生しました: {e}")
        print("以下の点を確認してください:")
        print("  - Excelがインストールされていますか？")
        print(f"  - '{WORKBOOK_NAME}' はExcelで開かれていますか？")
        print("  - MS2はログイン済みですか？")

if __name__ == "__main__":
    main()