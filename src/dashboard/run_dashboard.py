import os
from .app import create_app

def main():
    """
    ダッシュボードWebアプリケーションを起動します。
    """
    try:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        db_path = os.path.join(project_root, "results", "realtrade", "realtrade_state.db")

        if not os.path.exists(db_path):
            print(f"エラー: データベースファイルが見つかりません: {db_path}")
            print("先にリアルタイム取引を一度実行して、DBファイルを生成してください。")
            return

        app = create_app(db_path=db_path)
        print("--- リアルタイム監視ダッシュボード ---")
        print(f"DB Path: {db_path}")
        print("以下のURLにアクセスしてください:")
        print("http://127.0.0.1:5003/live")
        app.run(host='0.0.0.0', port=5003, debug=False)

    except ImportError as e:
        print(f"エラー: 必要なモジュールが見つかりません: {e}")
        print("プロジェクトの依存関係が正しくインストールされているか確認してください。")
    except Exception as e:
        print(f"ダッシュボードの起動中に予期せぬエラーが発生しました: {e}")


if __name__ == '__main__':
    main()