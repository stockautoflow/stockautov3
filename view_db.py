import sqlite3

def display_all_tables_data(db_file):
    """
    SQLiteデータベース内のすべてのテーブルとそのデータを表示します。

    Args:
        db_file (str): SQLiteデータベースファイルのパス。
    """
    conn = None
    try:
        # データベースに接続
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        print(f"データベース: '{db_file}' に接続しました。\n")

        # sqlite_master テーブルからすべてのテーブル名を取得
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("このデータベースにはテーブルがありません。")
            return

        print("--- データベース内のテーブル一覧とデータ ---")
        for table_tuple in tables:
            table_name = table_tuple[0]
            print(f"\n--- テーブル: '{table_name}' ---")

            try:
                # 各テーブルからすべてのデータを取得
                cursor.execute(f"SELECT * FROM {table_name};")
                rows = cursor.fetchall()

                # カラム名を取得 (オプション)
                # カラム名が必要な場合は、descriptionから取得できます
                column_names = [description[0] for description in cursor.description]
                print("カラム:", column_names)

                if not rows:
                    print(f"テーブル '{table_name}' は空です。")
                else:
                    for row in rows:
                        print(row)
            except sqlite3.OperationalError as e:
                print(f"エラー: テーブル '{table_name}' のデータを取得できませんでした。詳細: {e}")
            except Exception as e:
                print(f"予期せぬエラー: {e}")

    except sqlite3.Error as e:
        print(f"SQLite接続エラー: {e}")
    except Exception as e:
        print(f"予期せぬエラー: {e}")
    finally:
        if conn:
            conn.close()
            print(f"\nデータベース: '{db_file}' から切断しました。")

# 使用例:
if __name__ == "__main__":
    # ここに確認したいSQLiteデータベースファイルのパスを指定してください
    # 例: 'my_database.db', 'data/users.sqlite'
    database_file = 'realtrade/db/realtrade_state.db'
    # サンプルデータベースを作成（実行する前に削除するか、既存のDBを使用してください）
    # この部分をコメントアウトすると、既存のデータベースに接続します
    # create_sample_database(database_file) # 既にDBがある場合は不要です

    display_all_tables_data(database_file)


# --- (オプション) サンプルデータベースの作成関数 ---
def create_sample_database(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # テーブル1: users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                age INTEGER
            )
        ''')
        cursor.execute("INSERT INTO users (name, age) VALUES ('Alice', 30)")
        cursor.execute("INSERT INTO users (name, age) VALUES ('Bob', 24)")

        # テーブル2: products
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY,
                product_name TEXT NOT NULL,
                price REAL
            )
        ''')
        cursor.execute("INSERT INTO products (product_name, price) VALUES ('Laptop', 1200.00)")
        cursor.execute("INSERT INTO products (product_name, price) VALUES ('Mouse', 25.50)")
        cursor.execute("INSERT INTO products (product_name, price) VALUES ('Keyboard', 75.00)")

        # テーブル3: empty_table (空のテーブルの例)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS empty_table (
                item_id INTEGER PRIMARY KEY,
                description TEXT
            )
        ''')

        conn.commit()
        print(f"サンプルデータベース '{db_file}' を作成し、データを挿入しました。")
    except sqlite3.Error as e:
        print(f"サンプルデータベース作成エラー: {e}")
    finally:
        if conn:
            conn.close()