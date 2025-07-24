import sqlite3
import os
import yaml

def create_sample_database(db_file):
    """
    指定された内容で新しいSQLiteデータベースを作成します。
    既にファイルが存在する場合は上書きします。
    """
    # ファイルのディレクトリが存在しない場合は作成
    dir_name = os.path.dirname(db_file)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"既存のファイル '{db_file}' を削除しました。")

    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # 'positions' テーブルを作成
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT,
                size REAL,
                price REAL,
                entry_datetime TEXT
            )
        ''')

        # サンプルデータを挿入
        positions_data = [
            ('1332', 1100.0, 2222.0, '2025-01-01T09:09:09'),
            ('1605', 4400.0, 5555.0, '2025-04-04T14:04:04')
        ]
        cursor.executemany(
            'INSERT INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)',
            positions_data
        )

        conn.commit()
        print(f"✅ サンプルデータベース '{db_file}' を正常に作成しました。")

    except sqlite3.Error as e:
        print(f"❌ データベース作成エラー: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    CONFIG_FILE = 'config.yml'
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            if not config or 'sample_database_path' not in config:
                print(f"❌ エラー: '{CONFIG_FILE}' に 'sample_database_path' キーが見つかりません。")
            else:
                db_path = config['sample_database_path']
                create_sample_database(db_path)
    except FileNotFoundError:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' が見つかりません。")
    except yaml.YAMLError as e:
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' の形式が正しくありません。 詳細: {e}")