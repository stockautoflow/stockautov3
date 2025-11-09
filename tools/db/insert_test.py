import sqlite3
import os
import sys

# データベースファイルのパス
DB_FILE = os.path.join('log', 'notification_history.db')

# 挿入するSQL文 (IDは自動採番されるので含めません)
sql = """
INSERT INTO notification_history (
    timestamp, priority, recipient, subject, body, status, error_message
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""

# 挿入するデータ
data = (
    '2025-10-28 15:25:00.211122',
    'URGENT',
    'stockautoflow@gmail.com',
    '【RT】新規注文発注 (9999)',
    '日時: 2025-10-28T15:20:00\n銘柄: 9999\n方向: SELL\n数量: 10136.85\n価格: 986.5\nTP: 978.5\nSL: 990.5\n--- エントリー根拠 ---\nL: adx(14) [100.00] > [25] / M: BollingerBands(20,2.0) [986.98] > close [985.20] / S: rsi(14) [64.45] > [60]',
    'PENDING',
    None  # PythonでSQLのNULLを表す
)

conn = None
try:
    # データベースに接続
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # SQLを実行
    cursor.execute(sql, data)
    
    # 変更をコミット（確定）
    conn.commit()
    
    print(f"✅ データベース '{DB_FILE}' にテストデータを1行挿入しました。 (ID: {cursor.lastrowid})")
    print("モニターが起動していれば、メール通知が送信されます。")

except sqlite3.Error as e:
    print(f"❌ データベースエラー: {e}")
    if conn:
        conn.rollback() # エラーが発生した場合は変更を元に戻す
except Exception as e:
    print(f"❌ 予期せぬエラー: {e}")

finally:
    # 接続を閉じる
    if conn:
        conn.close()