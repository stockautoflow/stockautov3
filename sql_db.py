# --- スクリプトの使い方 ---
# このスクリプトは、コマンドライン引数としてSQLiteデータベースファイル名とSQLクエリを受け取り、
# 指定されたデータベースに対してSQLクエリを実行します。
#
# 使い方: python [スクリプト名.py] [データベースファイル名] "[実行したいSQLクエリ]"
#
# 例1: 'realtrade\db\realtrade_state.db' というデータベースに テストポジションを追加する
#   python sql_db.py realtrade\db\realtrade_state.db "INSERT INTO positions (symbol, size, price, entry_datetime) VALUES ('7270', 100, 5000, '2025-07-01T10:00:00')"
#
# 例1: 'realtrade\db\realtrade_state.db' というデータベースに 'users' テーブルを作成する
#   python sql_db.py realtrade\db\realtrade_state.db "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"
#
# 例2: 'users' テーブルに新しいユーザーを挿入する
#   python sql_db.py realtrade\db\realtrade_state.db "INSERT INTO users (name, age) VALUES ('Alice', 30)"
#
# 例3: 'users' テーブルからすべてのデータを取得する
#   python sql_db.py realtrade\db\realtrade_state.db "SELECT * FROM users"
#
# 例4: 'users' テーブルの 'Alice' の年齢を更新する
#   python sql_db.py realtrade\db\realtrade_state.db "UPDATE users SET age = 31 WHERE name = 'Alice'"
#
# 例5: 'users' テーブルから 'Alice' のデータを削除する
#   python sql_db.py realtrade\db\realtrade_state.db "DELETE FROM users WHERE name = 'Alice'"
# --- スクリプトの使い方 ここまで ---

import sqlite3
import argparse
import sys

def execute_sql(db_file, sql_query):
    """
    指定されたSQLiteデータベースファイルにSQLクエリを実行します。
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # SQLクエリの実行
        cursor.execute(sql_query)
        conn.commit()
        print(f"SQLクエリが正常に実行されました: {sql_query}")

        # SELECT文の場合、結果を表示
        if sql_query.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            if rows:
                print("\n--- 実行結果 ---")
                for row in rows:
                    print(row)
            else:
                print("結果はありませんでした。")

    except sqlite3.Error as e:
        print(f"データベースエラーが発生しました: {e}", file=sys.stderr)
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}", file=sys.stderr)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SQLiteデータベースにSQLクエリを実行します。")
    parser.add_argument("db_file", help="操作するSQLiteデータベースファイルのパス")
    parser.add_argument("sql_query", help="実行するSQLクエリ")

    args = parser.parse_args()

    execute_sql(args.db_file, args.sql_query)