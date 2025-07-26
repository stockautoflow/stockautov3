import sqlite3
import yaml
import os # <--- 追加

def display_all_tables_data(db_file):
    """
    SQLiteデータベース内のすべてのテーブルとそのデータを表示します。
    """
    conn = None
    try:
        # 読み取り専用モードで接続
        conn = sqlite3.connect(f'file:{db_file}?mode=ro', uri=True)
        cursor = conn.cursor()
        print(f"✅ データベース: '{db_file}' に接続しました。\n")

        # テーブル一覧を取得
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("データベースにテーブルが見つかりませんでした。")
            return

        print("--- データベース内のテーブル一覧とデータ ---")
        for table_tuple in tables:
            table_name = table_tuple[0]
            print(f"\n--- テーブル: '{table_name}' ---")

            try:
                cursor.execute(f"SELECT * FROM {table_name};")
                rows = cursor.fetchall()
                column_names = [description[0] for description in cursor.description]
                print("カラム:", column_names)

                if not rows:
                    print(f"テーブル '{table_name}' は空です。")
                else:
                    for row in rows:
                        print(row)
            except sqlite3.OperationalError as e:
                print(f"❌ エラー: テーブル '{table_name}' のデータを取得できませんでした。詳細: {e}")

    except sqlite3.OperationalError as e:
        print(f"❌ SQLite接続エラー: データベースファイルが見つからないか、読み取り専用で開けませんでした。パスを確認してください。 詳細: {e}")
    except Exception as e:
        print(f"❌ 予期せぬエラーが発生しました: {e}")
    finally:
        if conn:
            conn.close()
            print(f"\n✅ データベース: '{db_file}' から切断しました。")

if __name__ == "__main__":
    # --- ▼▼▼ ここから変更 ▼▼▼ ---
    # スクリプト自身の場所を基準にconfig.ymlへの絶対パスを構築
    script_dir = os.path.dirname(os.path.abspath(__file__))
    CONFIG_FILE = os.path.join(script_dir, 'config.yml')
    # --- ▲▲▲ ここまで変更 ▲▲▲ ---
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if not config or 'view_database_path' not in config:
                print(f"❌ エラー: '{CONFIG_FILE}' に 'view_database_path' キーが見つかりません。")
            else:
                db_path = config['view_database_path']
                display_all_tables_data(db_path)
    except FileNotFoundError:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' が見つかりません。")
    except yaml.YAMLError as e:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' の形式が正しくありません。 詳細: {e}")