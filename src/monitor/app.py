import sqlite3
import time
import json
import logging
import os
import csv # v1.13
from flask import Flask, render_template, Response, jsonify, g, request
from . import parser

# --- 定数 ---
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATABASE_PATH = os.path.join(PROJECT_ROOT, 'log', 'notification_history.db')
STOCKLIST_PATH = os.path.join(PROJECT_ROOT, 'config', 'stocklist.txt') # v1.13
POLL_INTERVAL = 1
HEARTBEAT_INTERVAL = 10

# --- Flaskアプリケーションのセットアップ ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.urandom(24)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- v1.16: 銘柄リストの読み込み (区切り文字修正) ---
stock_name_map = {}
encodings_to_try = ['utf-8', 'cp932'] # v1.15
stocklist_encoding = None

for enc in encodings_to_try:
    try:
        with open(STOCKLIST_PATH, 'r', encoding=enc) as f:
            # ▼▼▼【変更点】delimiter='	' を追加 ▼▼▼
            reader = csv.reader(f, delimiter='\t')
            # ▲▲▲【変更点】▲▲▲
            stock_name_map = {row[0]: row[1] for row in reader if len(row) >= 2}
        logger.info(f"{len(stock_name_map)} 件の銘柄名を {STOCKLIST_PATH} ({enc}) から読み込みました。")
        stocklist_encoding = enc
        break
    except FileNotFoundError:
        logger.warning(f"銘柄リスト {STOCKLIST_PATH} 未検出。コードのみ表示。")
        break
    except UnicodeDecodeError:
        logger.warning(f"{STOCKLIST_PATH} の {enc} 読込失敗。次を試行...")
        continue
    except Exception as e:
        logger.error(f"銘柄リスト ({STOCKLIST_PATH}) 読込エラー ({enc}): {e}")
        break

if not stock_name_map and os.path.exists(STOCKLIST_PATH):
     logger.error(f"{STOCKLIST_PATH} をどのエンコーディング ({', '.join(encodings_to_try)}) でも読み込めませんでした。")
# --- v1.16: ここまで ---


# --- DB接続ヘルパー ---
def get_db():
    if not hasattr(g, 'db_conn'):
        if not os.path.exists(DATABASE_PATH): logger.error(f"DB未検出: {DATABASE_PATH}"); g.db_conn = None
        else:
            try: g.db_conn = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True); g.db_conn.row_factory = sqlite3.Row
            except sqlite3.Error as e: logger.error(f"DB接続エラー: {e}"); g.db_conn = None
    return g.db_conn
@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db_conn') and g.db_conn is not None: g.db_conn.close()

# --- ルート定義 ---
@app.route('/')
def index(): return render_template('monitor_index.html')

@app.route('/get_initial_data')
def get_initial_data():
    conn = get_db();
    if conn is None: return jsonify({"error": "Database not found"}), 500
    try:
        cursor = conn.cursor(); cursor.execute("SELECT * FROM notification_history ORDER BY id DESC") # v1.7
        
        # ▼▼▼【変更箇所】▼▼▼
        # rows = cursor.fetchall(); parsed_data = [parser.parse_notification(row, stock_name_map) for row in rows]; parsed_data.reverse() # v1.13 map追加
        # last_id = parsed_data[-1]['id'] if parsed_data else 0; logger.info(f"初期データ {len(parsed_data)} 件ロード完了。")

        # [変更後]
        rows = cursor.fetchall(); parsed_data = [parser.parse_notification(row, stock_name_map) for row in rows] # .reverse() を削除
        last_id = parsed_data[0]['id'] if parsed_data else 0; logger.info(f"初期データ {len(parsed_data)} 件ロード完了。")
        # ▲▲▲【変更箇所ここまで】▲▲▲

        return jsonify({"data": parsed_data, "last_id": last_id})
    except sqlite3.Error as e: logger.error(f"初期データ取得エラー: {e}"); return jsonify({"error": str(e)}), 500

@app.route('/stream')
def stream():
    last_id_str = request.args.get('last_id', '0')
    try: current_last_id = int(last_id_str) # v1.6
    except ValueError: logger.warning(f"無効な last_id '{last_id_str}'。0 を使用。"); current_last_id = 0
    def event_stream(last_id_from_request):
        last_id = last_id_from_request; logger.info(f"SSE接続開始。最終ID: {last_id}"); yield "event: connected\ndata: {}\n\n"
        conn = None; last_heartbeat = time.time()
        while True:
            try:
                if conn is None:
                    if not os.path.exists(DATABASE_PATH): logger.warning(f"SSE: DB未検出: {DATABASE_PATH}。リトライ。"); time.sleep(POLL_INTERVAL * 5); continue
                    conn = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True); conn.row_factory = sqlite3.Row
                cursor = conn.cursor(); cursor.execute("SELECT * FROM notification_history WHERE id > ? ORDER BY id ASC", (last_id,))
                rows = cursor.fetchall()
                if rows:
                    new_data = [];
                    for row in rows: parsed_row = parser.parse_notification(row, stock_name_map); new_data.append(parsed_row); last_id = parsed_row['id'] # v1.13 map追加
                    yield f"data: {json.dumps(new_data)}\n\n"; last_heartbeat = time.time()
                elif (time.time() - last_heartbeat) > HEARTBEAT_INTERVAL: yield "event: heartbeat\ndata: {}\n\n"; last_heartbeat = time.time()
                time.sleep(POLL_INTERVAL)
            except sqlite3.Error as e: logger.warning(f"SSE DBエラー: {e}"); time.sleep(POLL_INTERVAL * 5); conn.close(); conn = None # v1.2 fix
            except GeneratorExit: logger.info(f"SSE接続切断。最終ID: {last_id}"); break
            except Exception as e: logger.error(f"SSE予期せぬエラー: {e}", exc_info=True); time.sleep(POLL_INTERVAL * 5); conn.close(); conn = None # v1.2 fix
        if conn: conn.close()
    return Response(event_stream(current_last_id), content_type='text/event-stream')

@app.route('/get_details/<int:record_id>')
def get_details(record_id):
    conn = get_db();
    if conn is None: return jsonify({"error": "Database not found"}), 500
    try:
        cursor = conn.cursor(); cursor.execute("SELECT subject, body, error_message FROM notification_history WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        if row: return jsonify({"subject": row['subject'], "body": row['body'], "error_message": row['error_message']})
        else: return jsonify({"error": "Record not found"}), 404
    except sqlite3.Error as e: logger.error(f"詳細データ取得エラー: {e}"); return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info(f"DB監視対象: {DATABASE_PATH}")
    if not os.path.exists(DATABASE_PATH): logger.warning("="*50); logger.warning(f"警告: DB未検出"); logger.warning("realtrade 開始で自動生成されます。"); logger.warning("="*50)
    app.run(debug=True, port=5003, use_reloader=False)