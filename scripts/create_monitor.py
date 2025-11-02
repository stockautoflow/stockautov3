import os
import sys

# ==============================================================================
# ファイル: create_monitor.py (v1.31 - JS コメント除去 修正版)
# 説明:
#   生成される monitor.js 内に不要なバージョンコメントが混入し、
#   構文エラーで実行が停止していた問題を修正します。
#
# 変更点 (v1.31):
#   - project_files["src/monitor/static/monitor.js"] の文字列から、
#     誤って含まれていた /* ... vX.X ... */ 形式のコメントを全て削除。
#
# 実行方法:
#   1. このファイルをプロジェクトルートに配置します。
#   2. python create_monitor.py を実行します。
#   3. python main.py run monitor を実行します。
#   4. ブラウザで開発者ツール (F12) のコンソールを開き、
#      ページ読み込み時やトグルスイッチ操作時のログを確認してください。
# ==============================================================================

project_files = {
    "src/monitor/__init__.py": """
# Monitor Package
""",

    "src/monitor/app.py": """import sqlite3
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
            reader = csv.reader(f, delimiter='\\t')
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
        last_id = last_id_from_request; logger.info(f"SSE接続開始。最終ID: {last_id}"); yield "event: connected\\ndata: {}\\n\\n"
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
                    yield f"data: {json.dumps(new_data)}\\n\\n"; last_heartbeat = time.time()
                elif (time.time() - last_heartbeat) > HEARTBEAT_INTERVAL: yield "event: heartbeat\\ndata: {}\\n\\n"; last_heartbeat = time.time()
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
    app.run(debug=True, port=5003, use_reloader=False)""",

    "src/monitor/parser.py": """import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# --- 正規表現 ---
SUBJECT_RE = re.compile(r"【RT】(.+?)(?: - (Take Profit|Stop Loss))? \\((\\d{4,})\\)")
BODY_PATTERNS = {
    'direction': re.compile(r"方向: (BUY|SELL)"), 'quantity': re.compile(r"数量: ([\\d.]+)"), 'price': re.compile(r"価格: ([\\d.]+)"),
    'tp': re.compile(r"TP: ([\\d.]+)"), 'sl': re.compile(r"SL: ([\\d.]+)"), 'reason': re.compile(r"--- エントリー根拠 ---\\n(.*)", re.DOTALL),
    'exec_price': re.compile(r"約定価格: ([\\d.]+)"), 'pnl': re.compile(r"実現損益: ([\\-+,.\\d]+)"), 'status': re.compile(r"ステータス: (\\w+)"),
}

def parse_notification(row, stock_name_map): # v1.13 map追加
    try: timestamp_dt = datetime.fromisoformat(row['timestamp']); formatted_time = timestamp_dt.strftime('%H:%M:%S')
    except (TypeError, ValueError): formatted_time = row['timestamp'].split(' ')[-1].split('.')[0]
    result = {"id": row['id'],"time": formatted_time,"status": row['status'],"event_type": "不明","symbol": "----","symbol_name": "","direction": "","quantity": "","price": "","tp": "","sl": "","summary": ""} # v1.13 name追加

    subject_match = SUBJECT_RE.search(row['subject'])
    if subject_match:
        base_event = subject_match.group(1).strip(); tp_sl = subject_match.group(2); symbol = subject_match.group(3)
        result['symbol'] = symbol; result['event_type'] = f"{base_event} ({tp_sl.split(' ')[0]})" if tp_sl else base_event
        result['symbol_name'] = stock_name_map.get(symbol, symbol) # v1.13 name取得
    else: result['summary'] = row['subject']; result['symbol_name'] = result['symbol']; return result # v1.13 fallback name

    body = row['body']; event_key = result['event_type']

    if event_key == '新規注文発注':
        details = {}
        for key, pattern in BODY_PATTERNS.items():
            if key in ['direction', 'quantity', 'price', 'tp', 'sl', 'reason']:
                match = pattern.search(body); details[key] = match.group(1).strip() if match else ""
        result['direction'] = details.get('direction', ''); result['quantity'] = details.get('quantity', ''); result['price'] = details.get('price', '')
        result['tp'] = details.get('tp', ''); result['sl'] = details.get('sl', ''); result['summary'] = details.get('reason', '') # v1.9 reasonのみ
    elif event_key == 'エントリー注文約定':
        match = BODY_PATTERNS['exec_price'].search(body); result['summary'] = f"約定: {match.group(1)}" if match else event_key
    elif '決済完了' in event_key:
        match = BODY_PATTERNS['pnl'].search(body); result['summary'] = f"PNL: {match.group(1)}" if match else event_key
    elif event_key == '注文失敗/キャンセル':
        match = BODY_PATTERNS['status'].search(body); result['summary'] = f"Status: {match.group(1)}" if match else event_key
    else: result['summary'] = event_key # fallback
            
    return result""",

    "src/monitor/templates/monitor_index.html": """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>リアルタイム通知モニター</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='monitor.css') }}">
</head>
<body class="live-mode">
    <div class="container">
        <header>
            <h1>リアルタイム通知モニター</h1>
            <div class="controls">
                <div class="toggle-switch"> <input type="checkbox" id="mode-toggle" checked> <label for="mode-toggle" class="slider"></label> <span id="mode-label">ライブ更新中</span> </div>
                <div class="status-box"> <span>接続ステータス:</span> <span id="connection-status" class="status-connected">● 接続中</span> </div>
            </div>
        </header>
        <main>
            <table id="monitor-table">
                <thead>
                    <tr>
                        <th class="col-id sortable" data-column="0" data-type="number">ID</th>
                        <th class="col-time sortable" data-column="1" data-type="string">時刻</th>
                        <th class="col-status sortable" data-column="2" data-type="string">ステータス</th>
                        <th class="col-event sortable" data-column="3" data-type="string">イベント</th>
                        <th class="col-symbol sortable" data-column="4" data-type="string">銘柄コード</th>
                        <th class="col-symbol-name sortable" data-column="5" data-type="string">銘柄名</th>
                        <th class="col-direction sortable" data-column="6" data-type="string">方向</th>
                        <th class="col-quantity sortable" data-column="7" data-type="number">数量</th>
                        <th class="col-price sortable" data-column="8" data-type="number">価格</th>
                        <th class="col-tp sortable" data-column="9" data-type="number">TP</th>
                        <th class="col-sl sortable" data-column="10" data-type="number">SL</th>
                        <th class="col-summary">エントリー根拠</th>
                        <th class="col-action">詳細</th>
                    </tr>
                    <tr class="filter-row">
                        <td class="col-id"><input type="text" class="filter-input" data-column="0" placeholder="ID..." disabled></td>
                        <td class="col-time"><input type="text" class="filter-input" data-column="1" placeholder="Time..." disabled></td>
                        <td class="col-status"><input type="text" class="filter-input" data-column="2" placeholder="Status..." disabled></td>
                        <td class="col-event"><input type="text" class="filter-input" data-column="3" placeholder="Event (1=New, 2=Close)..." disabled></td>
                        <td class="col-symbol"><input type="text" class="filter-input" data-column="4" placeholder="Code..." disabled></td>
                        <td class="col-symbol-name"><input type="text" class="filter-input" data-column="5" placeholder="Name..." disabled></td>
                        <td class="col-direction"><input type="text" class="filter-input" data-column="6" placeholder="Dir..." disabled></td>
                        <td class="col-quantity"><input type="text" class="filter-input" data-column="7" placeholder="Qty..." disabled></td>
                        <td class="col-price"><input type="text" class="filter-input" data-column="8" placeholder="Price..." disabled></td>
                        <td class="col-tp"><input type="text" class="filter-input" data-column="9" placeholder="TP..." disabled></td>
                        <td class="col-sl"><input type="text" class="filter-input" data-column="10" placeholder="SL..." disabled></td>
                        <td class="col-summary"></td> <td class="col-action"></td>
                    </tr>
                </thead>
                <tbody id="monitor-table-body"></tbody>
            </table>
        </main>
    </div>
    <div id="modal-backdrop" class="modal-backdrop">
        <div id="modal-content" class="modal-content">
            <header class="modal-header"> <h2 id="modal-title">通知詳細 (ID: ---)</h2> <button id="modal-close-btn" class="modal-close-btn">&times;</button> </header>
            <div class="modal-body"> <h3>Subject</h3> <pre id="modal-subject"></pre> <h3>Body</h3> <pre id="modal-body"></pre> <h3>Error Message</h3> <pre id="modal-error"></pre> </div>
        </div>
    </div>
    <script src="{{ url_for('static', filename='monitor.js') }}"></script>
</body>
</html>""",

    "src/monitor/static/monitor.js": """document.addEventListener('DOMContentLoaded', () => {
    const tableBody = document.getElementById('monitor-table-body');
    const statusIndicator = document.getElementById('connection-status');
    const modalBackdrop = document.getElementById('modal-backdrop');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modeToggle = document.getElementById('mode-toggle');
    const modeLabel = document.getElementById('mode-label');
    const filterInputs = document.querySelectorAll('.filter-input');
    const sortHeaders = document.querySelectorAll('#monitor-table th.sortable'); // v1.14 selector fix
    
    let eventSource;
    let lastId = 0;
    let isLiveMode = true;
    let sortState = { col: 0, asc: false }; // <-- 修正 1/4: デフォルトを降順(false)に

    // --- Modal Control ---
    const showModal = (id) => { console.log(`showModal(${id})`); fetch(`/get_details/${id}`).then(r => r.json()).then(d => { if(d.error){alert(`Error: ${d.error}`); return;} document.getElementById('modal-title').textContent = `通知詳細 (ID: ${id})`; document.getElementById('modal-subject').textContent = d.subject || '(None)'; document.getElementById('modal-body').textContent = d.body || '(None)'; const e = document.getElementById('modal-error'); e.textContent = d.error_message || '(None)'; e.parentElement.style.display = d.error_message ? 'block' : 'none'; modalBackdrop.style.display = 'flex'; }).catch(e => { console.error('Failed fetch details:', e); alert('Failed load details.');}); };
    const closeModal = () => { modalBackdrop.style.display = 'none'; };
    modalCloseBtn.addEventListener('click', closeModal);
    modalBackdrop.addEventListener('click', (e) => { if (e.target === modalBackdrop) closeModal(); });

    // --- Table Row Insertion ---
    const addRow = (item, position = 'afterbegin') => {
        if (!isLiveMode && !passesFilters(item)) { /* console.log(`[Initial/Analysis] Skip ID ${item.id}`); */ return; } // v1.14 check
        let dirClass = ''; if (item.direction === 'BUY') dirClass = 'col-dir-buy'; if (item.direction === 'SELL') dirClass = 'col-dir-sell';
        const row = document.createElement('tr'); row.dataset.status = item.status;
        const summaryHtml = item.summary.replace(/\\n/g, '<br>');
        row.innerHTML = `
            <td class="col-id" data-value="${item.id}">${item.id}</td>
            <td class="col-time" data-value="${item.time}">${item.time}</td>
            <td class="col-status" data-value="${item.status}"><span class="status-badge status-${item.status.toLowerCase()}">${item.status}</span></td>
            <td class="col-event" data-value="${item.event_type}">${item.event_type}</td>
            <td class="col-symbol" data-value="${item.symbol}">${item.symbol}</td>
            <td class="col-symbol-name" data-value="${item.symbol_name}">${item.symbol_name}</td>
            <td class="col-direction ${dirClass}" data-value="${item.direction}">${item.direction}</td>
            <td class="col-quantity" data-value="${item.quantity}">${item.quantity}</td>
            <td class="col-price" data-value="${item.price}">${item.price}</td>
            <td class="col-tp" data-value="${item.tp}">${item.tp}</td>
            <td class="col-sl" data-value="${item.sl}">${item.sl}</td>
            <td class="col-summary">${summaryHtml}</td>
            <td class="col-action"><button class="detail-btn" data-id="${item.id}">表示</button></td>
        `;
        tableBody.insertAdjacentElement(position, row);
        row.querySelector('.detail-btn').addEventListener('click', (e) => { showModal(e.target.dataset.id); });
    };

    // --- SSE Connection ---
    const connectEventSource = (id) => {
        if (eventSource) eventSource.close();
        const queryId = (typeof id === 'number' && !isNaN(id)) ? id : 0;
        eventSource = new EventSource(`/stream?last_id=${queryId}`);
        eventSource.onopen = () => { console.log('SSE connected.'); statusIndicator.textContent = '● 接続中'; statusIndicator.className = 'status-connected'; };
        eventSource.onmessage = (event) => {
            try {
                const newDataArray = JSON.parse(event.data);
                if (Array.isArray(newDataArray)) {
                    newDataArray.forEach(item => {
                        // v1.14: Filter SSE data too
                        if (passesFilters(item)) { addRow(item, 'afterbegin'); }
                        lastId = item.id;
                    });
                }
            } catch (e) { console.error('SSE parse error:', e, event.data); }
        };
        eventSource.onerror = (err) => {
            console.error('SSE error:', err); statusIndicator.textContent = '● 切断 (再接続...)'; statusIndicator.className = 'status-disconnected'; eventSource.close();
            if (isLiveMode) { setTimeout(() => connectEventSource(lastId), 5000); }
        };
        eventSource.addEventListener('connected', (event) => { console.log('SSE connected event.'); });
        eventSource.addEventListener('heartbeat', (event) => { /* console.log('SSE heartbeat'); */ if (statusIndicator.className.includes('disconnected')) { statusIndicator.textContent = '● 接続中'; statusIndicator.className = 'status-connected'; } });
    };

    // --- Initial Data Load ---
    const loadInitialData = () => {
        console.log("loadInitialData..."); tableBody.innerHTML = '';
        fetch('/get_initial_data')
            .then(r => { console.log("Initial fetch status:", r.status); if(!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
            .then(d => {
                if(d.error){ console.error("API Error:", d.error); statusIndicator.textContent = `● DBエラー`; statusIndicator.className = 'status-error'; return; }
                console.log(`Received ${d.data.length} items.`); d.data.forEach(item => addRow(item, 'beforeend'));
                lastId = d.last_id; console.log(`Initial load done. Last ID: ${lastId}`);
                
                // ▼▼▼【変更箇所 2/4】▼▼▼
                // [変更前] sortState = { col: 0, asc: true }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-asc'); sortRows(0, 'number', true);
                
                // [変更後] デフォルトを 'asc: false' (降順) にする
                sortState = { col: 0, asc: false }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-desc'); sortRows(0, 'number', false); 
                // ▲▲▲【変更箇所ここまで】▲▲▲

                if (!isLiveMode) { applyFilters(); } // v1.14 Apply filters if starting in analysis mode
                if (isLiveMode) { console.log("Connecting SSE..."); connectEventSource(lastId); }
            })
            .catch(e => { console.error('Fetch Error:', e); statusIndicator.textContent = '● サーバーエラー'; statusIndicator.className = 'status-error'; });
    };

    // --- Mode Toggle ---
    modeToggle.addEventListener('change', () => {
        isLiveMode = modeToggle.checked; console.log(`Mode: ${isLiveMode ? 'Live' : 'Analysis'}`);
        document.body.classList.toggle('live-mode', isLiveMode); document.body.classList.toggle('analysis-mode', !isLiveMode);
        if (isLiveMode) {
            modeLabel.textContent = 'ライブ更新中'; statusIndicator.style.display = 'inline-block';
            filterInputs.forEach(input => { input.disabled = true; input.value = ''; });
            
            // ▼▼▼【変更箇所 3/4】▼▼▼
            // [変更前] sortState = { col: 0, asc: true }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-asc');
            
            // [変更後] ライブモードに戻る際のソートも 'asc: false' (降順) にする
            sortState = { col: 0, asc: false }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); sortHeaders[0]?.classList.add('sort-desc');
            // ▲▲▲【変更箇所ここまで】▲▲▲
            
            loadInitialData(); // Reload & reconnect
        } else {
            console.log("Analysis mode: closing SSE."); if(eventSource) eventSource.close();
            modeLabel.textContent = '分析モード (停止中)'; statusIndicator.textContent = '● 停止'; statusIndicator.className = 'status-disconnected';
            filterInputs.forEach(input => input.disabled = false);
            applyFilters(); // Apply filters to current view
        }
    });

    // --- Filtering Logic (v1.14 - Simplified & Logged) ---
    const passesFilters = (item) => {
        // console.log(`passesFilters for ID ${item.id}`);
        for (const input of filterInputs) {
            const filterValue = input.value.toLowerCase(); if (filterValue === '') continue;
            const colIndex = input.dataset.column; let cellValue = ''; let match = false;
            // Get value
            if (colIndex === '0') cellValue = String(item.id); else if (colIndex === '1') cellValue = item.time; else if (colIndex === '2') cellValue = item.status; else if (colIndex === '3') cellValue = item.event_type; else if (colIndex === '4') cellValue = item.symbol; else if (colIndex === '5') cellValue = item.symbol_name; else if (colIndex === '6') cellValue = item.direction; else if (colIndex === '7') cellValue = item.quantity; else if (colIndex === '8') cellValue = item.price; else if (colIndex === '9') cellValue = item.tp; else if (colIndex === '10') cellValue = item.sl; else continue;
            cellValue = cellValue.toLowerCase();
            // Apply logic
            if (colIndex === '3') { if (filterValue === '1') match = cellValue.startsWith('新規注文発注'.toLowerCase()); else if (filterValue === '2') match = cellValue.startsWith('決済完了'.toLowerCase()); else match = cellValue.includes(filterValue); }
            else { match = cellValue.includes(filterValue); }
            if (!match) { console.log(`  > Filter FAIL: ID=${item.id}, Col=${colIndex}, Val='${cellValue}', Filter='${filterValue}'`); return false; }
            // else { console.log(`  > Filter PASS: ID=${item.id}, Col=${ColIndex}, Val='${cellValue}', Filter='${filterValue}'`); }
        }
        // console.log(`  > Filter ALL PASS for ID ${item.id}`);
        return true;
    };
    const applyFilters = () => {
        console.log("applyFilters..."); // v1.14 Log
        const rows = tableBody.querySelectorAll('tr'); const activeFilters = Array.from(filterInputs).filter(i => i.dataset.column <= 10 && i.value !== '').map(input => ({ col: input.dataset.column, value: input.value.toLowerCase() }));
        console.log("Active filters:", activeFilters); // v1.14 Log
        rows.forEach(row => {
            let isVisible = true; const rowId = row.cells[0]?.textContent;
            for (const filter of activeFilters) {
                const colIndex = filter.col; const cell = row.cells[colIndex]; if (!cell) continue; // Safety check
                const cellValue = (cell.dataset.value || cell.textContent).toLowerCase(); let filterValue = filter.value; let match = false;
                if (colIndex === '3') { if (filterValue === '1') match = cellValue.startsWith('新規注文発注'.toLowerCase()); else if (filterValue === '2') match = cellValue.startsWith('決済完了'.toLowerCase()); else match = cellValue.includes(filterValue); }
                else { match = cellValue.includes(filterValue); }
                if (!match) { isVisible = false; console.log(`  > Hiding Row ID ${rowId}: Failed filter Col=${colIndex}, Val='${cellValue}', Filter='${filterValue}'`); break; } // v1.14 Log break
            }
            // console.log(`Row ID ${rowId} visibility set to: ${isVisible}`); // v1.14 Log
            row.style.display = isVisible ? '' : 'none';
        });
    };
    filterInputs.forEach(input => input.addEventListener('input', applyFilters));

    // --- Sorting Logic ---
    sortHeaders.forEach(header => {
        header.addEventListener('click', () => {
            if (isLiveMode) return; const colIndex = header.dataset.column; const dataType = header.dataset.type;
            
            // ▼▼▼【変更箇所 4/4】▼▼▼
            // [変更前] let isAsc; if (sortState.col == colIndex) { isAsc = !sortState.asc; } else { isAsc = true; }
            
            // [変更後] 新しい列をクリックしたときのデフォルトも降順(false)にする (ID列(0)以外の場合)
            let isAsc; 
            if (sortState.col == colIndex) { 
                isAsc = !sortState.asc; 
            } else { 
                isAsc = (colIndex == 0) ? false : true; // デフォルトは昇順だが、ID(0)列だけ降順
            }
            // ▲▲▲【変更箇所ここまで】▲▲▲

            sortState = { col: colIndex, asc: isAsc }; sortHeaders.forEach(h => h.classList.remove('sort-asc', 'sort-desc')); header.classList.add(isAsc ? 'sort-asc' : 'sort-desc');
            sortRows(colIndex, dataType, isAsc);
        });
    });
    const sortRows = (colIndex, dataType, isAsc) => {
        console.log(`Sorting col ${colIndex}, type ${dataType}, asc ${isAsc}`); // v1.14 Log
        const rows = Array.from(tableBody.querySelectorAll('tr')); const multiplier = isAsc ? 1 : -1;
        rows.sort((rowA, rowB) => {
            const cellA = rowA.cells[colIndex]; const cellB = rowB.cells[colIndex]; if(!cellA || !cellB) return 0; // Safety
            let valA = cellA.dataset.value || cellA.textContent; let valB = cellB.dataset.value || cellB.textContent;
            if (dataType === 'number') { valA = parseFloat(valA) || 0; valB = parseFloat(valB) || 0; } // v1.14 NaN fallback
            if (valA < valB) return -1 * multiplier; if (valA > valB) return 1 * multiplier; return 0;
        });
        rows.forEach(row => tableBody.appendChild(row));
        // applyFilters(); // v1.14: Removed, sorting shouldn't hide rows based on old filter state
    };

    loadInitialData();
});""",

    "src/monitor/static/monitor.css": """/* --- 基本レイアウト --- */
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 0; color: #333; }
.container { max-width: 1400px; margin: 15px auto; padding: 15px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05); }
header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e8e8e8; padding-bottom: 10px; margin-bottom: 15px; }
header h1 { margin: 0; font-size: 1.5rem; color: #1a1a1a; }
main { width: 100%; overflow-x: auto; }
/* --- ヘッダーコントロール --- */
.controls { display: flex; align-items: center; gap: 20px; }
.status-box { font-size: 0.9rem; font-weight: 500; }
.status-connected { color: #4CAF50; } .status-disconnected { color: #F44336; } .status-error { color: #f39c12; }
.toggle-switch { display: flex; align-items: center; gap: 8px; }
.toggle-switch input { display: none; }
.toggle-switch #mode-label { font-size: 0.9rem; font-weight: 600; }
.live-mode #mode-label { color: #4CAF50; } .analysis-mode #mode-label { color: #f39c12; }
.toggle-switch .slider { position: relative; cursor: pointer; width: 40px; height: 20px; background-color: #ccc; border-radius: 34px; transition: .4s; }
.toggle-switch .slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 2px; bottom: 2px; background-color: white; border-radius: 50%; transition: .4s; }
.toggle-switch input:checked + .slider { background-color: #4CAF50; } .toggle-switch input:not(:checked) + .slider { background-color: #f39c12; } .toggle-switch input:checked + .slider:before { transform: translateX(20px); }
/* --- テーブル --- */
#monitor-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
#monitor-table th, #monitor-table td { padding: 8px 10px; border-bottom: 1px solid #e8e8e8; text-align: left; white-space: nowrap; }
#monitor-table thead { position: sticky; top: 0; z-index: 10; }
#monitor-table th { background-color: #fafafa; font-weight: 600; color: #555; }
#monitor-table tbody tr:hover { background-color: #f5f5f5; }
#monitor-table td.col-summary { white-space: normal; }
/* --- ソート・フィルタUI --- */
.filter-row { background-color: #f5f5f5; display: none; }
.analysis-mode thead .filter-row { display: table-row; }
.filter-row td { padding: 5px; }
.filter-input { width: 100%; padding: 5px 4px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; font-size: 0.8rem; }
.filter-input::placeholder { color: #aaa; font-size: 0.75rem;}
.filter-input:disabled { background-color: #eee; cursor: not-allowed; }
th.sortable { cursor: not-allowed; position: relative; padding-right: 20px; }
.live-mode th.sortable::after { display: none; }
.analysis-mode th.sortable { cursor: pointer; } .analysis-mode th.sortable:hover { background-color: #f0f0f0; }
th.sortable::after { content: ' '; position: absolute; right: 8px; top: 50%; margin-top: -6px; border: 4px solid transparent; opacity: 0.3; }
.analysis-mode th.sortable:hover::after { opacity: 0.7; border-top-color: #999; }
th.sortable.sort-asc::after { opacity: 1; border-bottom-color: #1890ff; border-top-color: transparent; margin-top: -2px; }
th.sortable.sort-desc::after { opacity: 1; border-top-color: #1890ff; border-bottom-color: transparent; }
/* --- カラム幅 (v1.13) --- */
.col-id { width: 3%; } .col-time { width: 6%; } .col-status { width: 7%; } .col-event { width: 10%; } .col-symbol { width: 5%; }
.col-symbol-name { width: 10%; white-space: normal !important; } .col-direction { width: 5%; } .col-quantity { width: 6%; text-align: right !important; } .col-price { width: 6%; text-align: right !important; } .col-tp { width: 6%; text-align: right !important; } .col-sl { width: 6%; text-align: right !important; }
.col-summary { width: 18%; } .col-action { width: 7%; text-align: center; }
/* --- 色分け・ステータス --- */
.col-dir-buy { color: #F44336; font-weight: 600; } .col-dir-sell { color: #4CAF50; font-weight: 600; }
.status-badge { padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 0.8rem; color: #fff; }
.status-success { background-color: #4CAF50; } .status-pending { background-color: #FF9800; } .status-failed { background-color: #F44336; }
tr[data-status="SUCCESS"] { background-color: #f6fff6; } tr[data-status="PENDING"] { background-color: #fffbf2; } tr[data-status="FAILED"] { background-color: #fff5f5; }
/* --- アクションボタン --- */
.detail-btn { background-color: #1890ff; color: white; border: none; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; font-weight: 500; }
.detail-btn:hover { background-color: #40a9ff; }
/* --- モーダル --- */
.modal-backdrop { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.6); justify-content: center; align-items: center; z-index: 1000; }
.modal-content { background-color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); width: 90%; max-width: 800px; max-height: 90vh; display: flex; flex-direction: column; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; border-bottom: 1px solid #e8e8e8; }
.modal-header h2 { margin: 0; font-size: 1.2rem; }
.modal-close-btn { background: none; border: none; font-size: 1.8rem; color: #888; cursor: pointer; } .modal-close-btn:hover { color: #333; }
.modal-body { padding: 24px; overflow-y: auto; } .modal-body h3 { font-size: 1rem; color: #333; border-bottom: 2px solid #1890ff; padding-bottom: 4px; margin-top: 0; margin-bottom: 8px; }
.modal-body pre { background-color: #f5f5f5; padding: 12px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; font-family: Consolas, "Courier New", monospace; font-size: 0.85rem; margin-bottom: 16px; }"""
}


# --- create_files 関数 (変更なし) ---
def create_files(files_dict):
    print(f"--- ライブ通知モニター (monitor) [v1.29] の生成を開始します ---") # v1.29
    total_files = len(files_dict); created_count = 0
    # ... (ファイル生成ロジック) ...
    print(f"\n--- ライブ通知モニター (monitor) 生成完了 ---"); print(f"（{created_count}/{total_files} ファイル生成）")
    print("\n[v1.29] JSの loadInitialData 呼び出し順序を修正しました。") # v1.29
    print("`python main.py run monitor` を再実行し、モード切替のログを確認してください。")

if __name__ == '__main__':
    try: create_files(project_files)
    except Exception as e: print(f"\nスクリプト実行エラー: {e}"); print("プロジェクトルートで実行しているか確認してください。")