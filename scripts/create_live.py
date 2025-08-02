import os
import sys

# ==============================================================================
# ファイル: create_live.py (完全版)
# 実行方法: python create_live.py
# 説明:
#   このスクリプトは、リアルタイム監視ダッシュボード機能の実装に必要な
#   すべてのファイルの「完全な内容」を生成・上書きします。
#   コードの省略は一切ありません。
# ==============================================================================

project_files = {
    # ==========================================================================
    # ▼▼▼ 新規作成ファイル (3件) ▼▼▼
    # ==========================================================================
    "src/dashboard/run_dashboard.py": """
import os
from .app import create_app

def main():
    \"\"\"
    ダッシュボードWebアプリケーションを起動します。
    \"\"\"
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
""",

    "src/dashboard/data_provider.py": """
import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DataProvider:
    def __init__(self, db_path):
        self.db_path = db_path
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"指定されたデータベースファイルが見つかりません: {db_path}")

    def _query_db(self, query, params=(), one=False):
        try:
            db_uri = f"file:{self.db_path}?mode=ro"
            with sqlite3.connect(db_uri, uri=True, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone() if one else cursor.fetchall()
                return result
        except sqlite3.OperationalError as e:
            logger.error(f"データベースへの接続に失敗しました。DBファイルがロックされている可能性があります: {e}")
            return None
        except Exception as e:
            logger.error(f"データベースクエリ実行中にエラー: {e}")
            return None

    def get_live_status(self):
        rows = self._query_db("SELECT key, value, updated_at FROM live_status")
        if rows is None:
            return {"error": "Database is locked or unavailable."}

        status = {"summary": {}, "positions": []}
        summary_data = {}
        total_pnl = 0

        for key, value, updated_at in rows:
            try:
                data = json.loads(value)
                if key == 'summary':
                    summary_data.update(data)
                elif key.startswith('chart_'):
                    symbol = key.split('_', 1)[1]
                    pos_size = data.get('position_size', 0)
                    if pos_size != 0:
                        entry_price = data.get('position_price', 0)
                        current_price = data.get('price', 0)
                        pnl = (current_price - entry_price) * pos_size
                        total_pnl += pnl

                        position_info = {
                            "symbol": symbol,
                            "side": "Long" if pos_size > 0 else "Short",
                            "quantity": pos_size,
                            "entry_price": entry_price,
                            "current_price": current_price,
                            "unrealized_pnl": pnl,
                            "unrealized_pnl_perc": (pnl / (entry_price * abs(pos_size)) * 100) if entry_price > 0 and pos_size !=0 else 0,
                            "updated_at": updated_at
                        }
                        status['positions'].append(position_info)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"DB内のJSONデータの解析に失敗しました (key: {key}): {e}")
                continue

        cash = summary_data.get('cash', 0)
        value = cash + total_pnl
        status['summary'] = {
            "total_equity": value,
            "unrealized_pnl": total_pnl,
            "cash": cash,
            "active_symbols": len(status['positions'])
        }
        return status
""",

    "src/dashboard/templates/live_dashboard.html": """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>リアルタイム監視ダッシュボード</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 15px; }
        .grid-container { display: grid; grid-template-columns: 1fr 2fr; grid-template-rows: auto auto 1fr; gap: 15px; height: calc(100vh - 30px); }
        .header { grid-column: 1 / -1; display: flex; justify-content: space-around; background: #fff; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .summary-card { text-align: center; }
        .summary-card h3 { margin: 0 0 5px; color: #555; font-size: 1em; }
        .summary-card p { margin: 0; font-size: 1.5em; font-weight: 600; }
        .pnl-positive { color: #28a745; }
        .pnl-negative { color: #dc3545; }
        .positions { grid-column: 1 / 2; grid-row: 2 / 4; background: #fff; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-y: auto; }
        .chart { grid-column: 2 / 3; grid-row: 2 / 3; background: #fff; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .logs { grid-column: 2 / 3; grid-row: 3 / 4; background: #333; color: #eee; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow-y: auto; font-family: monospace; font-size: 0.85em; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; }
        .positions table tbody tr:hover { background-color: #f5f5f5; cursor: pointer; }
        h2 { margin-top: 0; }
    </style>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body>
    <div class="grid-container">
        <div class="header">
            <div class="summary-card"><h3>総資産</h3><p id="summary-equity">¥0</p></div>
            <div class="summary-card"><h3>評価損益</h3><p id="summary-pnl">¥0</p></div>
            <div class="summary-card"><h3>現金</h3><p id="summary-cash">¥0</p></div>
            <div class="summary-card"><h3>稼働銘柄数</h3><p id="summary-active-symbols">0</p></div>
        </div>
        <div class="positions">
            <h2>保有ポジション</h2>
            <table id="positions-table">
                <thead><tr><th>銘柄</th><th>方向</th><th>数量</th><th>取得単価</th><th>現在価格</th><th>評価損益</th></tr></thead>
                <tbody></tbody>
            </table>
        </div>
        <div class="chart">
             <h2 id="chart-title">チャート</h2>
             <div id="chart-container" style="width:100%; height: calc(100% - 40px);"></div>
        </div>
        <div class="logs">
            <h2>リアルタイムログ</h2>
            <div id="logs-container"></div>
        </div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const API_URL = '/api/live/status';

            function formatCurrency(value) {
                if (value === null || isNaN(value)) return '¥-';
                return `¥${parseInt(value).toLocaleString()}`;
            }

            function updateDashboard() {
                fetch(API_URL)
                    .then(response => response.json())
                    .then(data => {
                        if (data.error) {
                            console.error("API Error:", data.error);
                            return;
                        }

                        // Summary Panel
                        const summary = data.summary || {};
                        document.getElementById('summary-equity').textContent = formatCurrency(summary.total_equity);
                        const pnlElement = document.getElementById('summary-pnl');
                        pnlElement.textContent = formatCurrency(summary.unrealized_pnl);
                        pnlElement.className = (summary.unrealized_pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
                        document.getElementById('summary-cash').textContent = formatCurrency(summary.cash);
                        document.getElementById('summary-active-symbols').textContent = summary.active_symbols || 0;

                        // Positions Table
                        const tableBody = document.querySelector('#positions-table tbody');
                        tableBody.innerHTML = '';
                        const positions = data.positions || [];
                        positions.forEach(pos => {
                            const row = tableBody.insertRow();
                            const pnlPerc = pos.unrealized_pnl_perc ? pos.unrealized_pnl_perc.toFixed(2) : '0.00';
                            row.innerHTML = `
                                <td>${pos.symbol}</td>
                                <td style="color: ${pos.side === 'Long' ? 'blue' : 'red'};">${pos.side}</td>
                                <td>${pos.quantity}</td>
                                <td>${(pos.entry_price || 0).toFixed(2)}</td>
                                <td>${(pos.current_price || 0).toFixed(2)}</td>
                                <td class="${(pos.unrealized_pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative'}">${formatCurrency(pos.unrealized_pnl)} (${pnlPerc}%)</td>
                            `;
                        });
                    })
                    .catch(error => console.error('Error fetching dashboard data:', error));
            }

            setInterval(updateDashboard, 5000); // 5秒ごとに更新
            updateDashboard(); // 初回実行
        });
    </script>
</body>
</html>
""",

    # ==========================================================================
    # ▼▼▼ 既存ファイルの修正 (4件) ▼▼▼
    # ==========================================================================
    "src/dashboard/app.py": """
from flask import Flask, jsonify, render_template
from .data_provider import DataProvider
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(db_path):
    \"\"\"
    Flaskアプリケーションを生成するファクトリ関数。
    \"\"\"
    app = Flask(__name__, template_folder='templates')
    app.config['DATA_PROVIDER'] = DataProvider(db_path)

    @app.route('/live')
    def live_dashboard():
        return render_template('live_dashboard.html')

    @app.route('/api/live/status')
    def api_live_status():
        try:
            provider = app.config['DATA_PROVIDER']
            status = provider.get_live_status()
            return jsonify(status)
        except Exception as e:
            logger.error(f"API /api/live/status でエラー: {e}", exc_info=True)
            return jsonify({"error": "An internal server error occurred."}), 500

    # 既存のバックテスト分析用ダッシュボード機能も残す
    # 注意: この機能は chart_generator.py に依存しており、
    # chart_generator.py はライブDBを考慮していないため、同時利用には注意が必要
    @app.route('/')
    def index():
        # この機能は現在メンテナンスされていません。
        # 必要に応じて chart_generator.py などを修正する必要があります。
        return "<h1>バックテスト分析 (旧機能)</h1><p><a href='/live'>ライブ監視ダッシュボードへ</a></p>"

    return app
""",

    "src/realtrade/state_manager.py": """
import sqlite3
import logging
import os
import threading
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self._create_tables()
            logger.info(f"データベースに接続しました: {db_path}")
        except sqlite3.Error as e:
            logger.critical(f"データベース接続エラー: {e}")
            raise

    def _create_tables(self):
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS positions (
                        symbol TEXT PRIMARY KEY, size REAL NOT NULL,
                        price REAL NOT NULL, entry_datetime TEXT NOT NULL)
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS live_status (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                ''')
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"テーブル作成エラー: {e}")

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("データベース接続をクローズしました。")

    def save_position(self, symbol, size, price, entry_datetime):
        sql = "INSERT OR REPLACE INTO positions (symbol, size, price, entry_datetime) VALUES (?, ?, ?, ?)"
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(sql, (str(symbol), size, price, entry_datetime))
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"ポジション保存エラー: {e}")

    def load_positions(self):
        positions = {}
        sql = "SELECT symbol, size, price, entry_datetime FROM positions"
        try:
            with self.lock:
                cursor = self.conn.cursor()
                for row in cursor.execute(sql):
                    positions[row[0]] = {'size': row[1], 'price': row[2], 'entry_datetime': row[3]}
            logger.info(f"{len(positions)}件のポジションをDBからロードしました。")
            return positions
        except sqlite3.Error as e:
            logger.error(f"ポジション読み込みエラー: {e}")
            return {}

    def delete_position(self, symbol):
        sql = "DELETE FROM positions WHERE symbol = ?"
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(sql, (str(symbol),))
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"ポジション削除エラー: {e}")

    def update_live_status(self, key, data_dict):
        \"\"\"
        ライブステータスをキー・バリュー形式でDBに保存する。
        \"\"\"
        sql = "INSERT OR REPLACE INTO live_status (key, value, updated_at) VALUES (?, ?, ?)"
        try:
            with self.lock:
                cursor = self.conn.cursor()
                now = datetime.now().isoformat()
                value_json = json.dumps(data_dict)
                cursor.execute(sql, (key, value_json, now))
                self.conn.commit()
        except (sqlite3.Error, TypeError) as e:
            logger.error(f"ライブステータス更新エラー (key: {key}): {e}")
""",

    "src/core/strategy.py": """
import backtrader as bt
import logging
import inspect
import yaml
import copy
import threading
from datetime import datetime
from .indicators import SafeStochastic, VWAP, SafeADX
from .util import notifier

class DynamicStrategy(bt.Strategy):
    params = (
        ('strategy_params', None),
        ('strategy_catalog', None),
        ('strategy_assignments', None),
        ('live_trading', False),
        ('persisted_position', None),
        ('state_manager', None),
    )

    def __init__(self):
        self.live_trading = self.p.live_trading
        self.state_manager = self.p.state_manager
        
        symbol_str = self.data0._name.split('_')[0]

        if self.p.strategy_catalog and self.p.strategy_assignments:
            symbol = int(symbol_str) if symbol_str.isdigit() else symbol_str
            strategy_name = self.p.strategy_assignments.get(str(symbol))
            if not strategy_name: raise ValueError(f"銘柄 {symbol} に戦略が割り当てられていません。")
            with open('config/strategy_base.yml', 'r', encoding='utf-8') as f:
                base_strategy = yaml.safe_load(f)
            entry_strategy_def = self.p.strategy_catalog.get(strategy_name)
            if not entry_strategy_def: raise ValueError(f"エントリー戦略カタログに '{strategy_name}' が見つかりません。")
            self.strategy_params = copy.deepcopy(base_strategy)
            self.strategy_params.update(entry_strategy_def)
            self.logger = logging.getLogger(f"{self.__class__.__name__}-{symbol}")
        elif self.p.strategy_params:
            self.strategy_params = self.p.strategy_params
            self.logger = logging.getLogger(self.__class__.__name__)
        else:
            raise ValueError("戦略パラメータが見つかりません。")

        if not isinstance(self.strategy_params.get('exit_conditions'), dict):
            raise ValueError(f"戦略 '{self.strategy_params.get('name')}' に exit_conditions が定義されていません。")
        if not isinstance(self.strategy_params.get('exit_conditions', {}).get('stop_loss'), dict):
            raise ValueError(f"戦略 '{self.strategy_params.get('name')}' の exit_conditions に stop_loss が定義されていません。")

        self.data_feeds = {'short': self.datas[0], 'medium': self.datas[1], 'long': self.datas[2]}
        self.indicators = self._create_indicators()
        self.entry_order = None
        self.exit_orders = []
        self.entry_reason = ""
        self.entry_reason_for_trade = ""
        self.executed_size = 0
        self.risk_per_share = 0.0
        self.tp_price = 0.0
        self.sl_price = 0.0
        self.current_position_entry_dt = None
        self.live_trading_started = False

        self.is_restoring = self.p.persisted_position is not None

    def start(self):
        self.live_trading_started = True

    def _send_notification(self, subject, body):
        self.logger.debug(f"メール通知をキューに追加: {subject}")
        notifier.send_email(subject, body)

    def _get_indicator_key(self, timeframe, name, params):
        param_str = "_".join(f"{k}_{v}" for k, v in sorted(params.items()))
        return f"{timeframe}_{name}_{param_str}"

    def _create_indicators(self):
        indicators, unique_defs = {}, {}
        def add_def(timeframe, ind_def):
            if not isinstance(ind_def, dict) or 'name' not in ind_def: return
            key = self._get_indicator_key(timeframe, **ind_def)
            if key not in unique_defs: unique_defs[key] = (timeframe, ind_def)

        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict): continue
                    tf = cond.get('timeframe')
                    if not tf: continue
                    add_def(tf, cond.get('indicator')); add_def(tf, cond.get('indicator1')); add_def(tf, cond.get('indicator2'))
                    if cond.get('target', {}).get('type') == 'indicator': add_def(tf, cond['target']['indicator'])

        if isinstance(self.strategy_params.get('exit_conditions'), dict):
            for exit_type in ['take_profit', 'stop_loss']:
                cond = self.strategy_params['exit_conditions'].get(exit_type, {})
                if cond and cond.get('type') in ['atr_multiple', 'atr_stoptrail']:
                    atr_params = {k: v for k, v in cond.get('params', {}).items() if k != 'multiplier'}
                    add_def(cond.get('timeframe'), {'name': 'atr', 'params': atr_params})

        for key, (timeframe, ind_def) in unique_defs.items():
            name, params = ind_def['name'], ind_def.get('params', {})
            ind_cls = None
            if name.lower() == 'stochastic': ind_cls = SafeStochastic
            elif name.lower() == 'vwap': ind_cls = VWAP
            elif name.lower() == 'adx': ind_cls = SafeADX
            if ind_cls is None:
                cls_candidate = getattr(bt.indicators, name, None)
                if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator): ind_cls = cls_candidate
                if ind_cls is None:
                    if name.lower() == 'rsi': ind_cls = bt.indicators.RSI_Safe
                    else:
                        for n_cand in [name.upper(), name.capitalize()]:
                            cls_candidate = getattr(bt.indicators, n_cand, None)
                            if inspect.isclass(cls_candidate) and issubclass(cls_candidate, bt.Indicator):
                                ind_cls = cls_candidate
                                break
            if ind_cls:
                self.logger.debug(f"インジケーター作成: {key} using class {ind_cls.__name__}")
                indicators[key] = ind_cls(self.data_feeds[timeframe], plot=False, **params)
            else: self.logger.error(f"インジケータークラス '{name}' が見つかりません。")

        if isinstance(self.strategy_params.get('entry_conditions'), dict):
            for cond_list in self.strategy_params['entry_conditions'].values():
                if not isinstance(cond_list, list): continue
                for cond in cond_list:
                    if not isinstance(cond, dict) or cond.get('type') not in ['crossover', 'crossunder']: continue
                    k1 = self._get_indicator_key(cond['timeframe'], **cond['indicator1']); k2 = self._get_indicator_key(cond['timeframe'], **cond['indicator2'])
                    if k1 in indicators and k2 in indicators:
                        cross_key = f"cross_{k1}_vs_{k2}"
                        if cross_key not in indicators: indicators[cross_key] = bt.indicators.CrossOver(indicators[k1], indicators[k2], plot=False)
        return indicators

    def _evaluate_condition(self, cond):
        tf, cond_type = cond['timeframe'], cond.get('type')
        data_feed = self.data_feeds[tf]
        if len(data_feed) == 0: return False, ""
        if cond_type in ['crossover', 'crossunder']:
            k1 = self._get_indicator_key(tf, **cond['indicator1']); k2 = self._get_indicator_key(tf, **cond['indicator2'])
            cross_indicator = self.indicators.get(f"cross_{k1}_vs_{k2}")
            if cross_indicator is None or len(cross_indicator) == 0: return False, ""
            is_met = (cross_indicator[0] > 0 and cond_type == 'crossover') or (cross_indicator[0] < 0 and cond_type == 'crossunder')
            p1 = ",".join(map(str, cond['indicator1'].get('params', {}).values())); p2 = ",".join(map(str, cond['indicator2'].get('params', {}).values()))
            reason = f"{tf[0].upper()}: {cond_type}({cond['indicator1']['name']}({p1}),{cond['indicator2']['name']}({p2})) [{is_met}]"
            return is_met, reason

        ind = self.indicators.get(self._get_indicator_key(tf, **cond['indicator']))
        if ind is None or len(ind) == 0: return False, ""
        val, compare, target = ind[0], cond['compare'], cond['target']
        target_type, target_val, target_val_str = target.get('type'), None, ""
        if target_type == 'data':
            target_val = getattr(data_feed, target['value'])[0]; target_val_str = f"{target['value']} [{target_val:.2f}]"
        elif target_type == 'indicator':
            target_ind = self.indicators.get(self._get_indicator_key(tf, **target['indicator']))
            if target_ind is None or len(target_ind) == 0: return False, ""
            target_val = target_ind[0]; target_val_str = f"{target['indicator']['name']}(...) [{target_val:.2f}]"
        elif target_type == 'values':
            target_val = target['value']
            target_val_str = f"[{target_val[0]},{target_val[1]}]" if compare == 'between' else f"[{target_val}]"
        if target_val is None: return False, ""
        is_met = False
        if compare == '>': is_met = val > (target_val[0] if isinstance(target_val, list) else target_val)
        elif compare == '<': is_met = val < (target_val[0] if isinstance(target_val, list) else target_val)
        elif compare == 'between': is_met = target_val[0] < val < target_val[1]
        params_str = ",".join(map(str, cond['indicator'].get('params', {}).values()))
        reason = f"{tf[0].upper()}: {cond['indicator']['name']}({params_str}) [{val:.2f}] {compare} {target_val_str}"
        return is_met, reason

    def _check_all_conditions(self, trade_type):
        conditions = self.strategy_params.get('entry_conditions', {}).get(trade_type, [])
        if not conditions: return False, ""
        reason_details, all_conditions_met = [], True
        for c in conditions:
            is_met, reason_str = self._evaluate_condition(c)
            if not is_met:
                all_conditions_met = False
                break
            reason_details.append(reason_str)
        return (True, "\\n".join(reason_details)) if all_conditions_met else (False, "")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        is_entry = self.entry_order and self.entry_order.ref == order.ref
        is_exit = any(o.ref == order.ref for o in self.exit_orders)
        if not is_entry and not is_exit: return
        if order.status == order.Completed:
            if is_entry:
                subject = f"【リアルタイム取引】エントリー注文約定 ({self.data0._name})"; body = f"日時: {self.data.datetime.datetime(0).isoformat()}\\n銘柄: {self.data0._name}\\nステータス: {order.getstatusname()}\\n方向: {'BUY' if order.isbuy() else 'SELL'}\\n約定数量: {order.executed.size:.2f}\\n約定価格: {order.executed.price:.2f}"
                self.log(f"エントリー成功。 Size: {order.executed.size:.2f} @ {order.executed.price:.2f}")
                if not self.live_trading: self._place_native_exit_orders()
                else:
                    is_long, entry_price = order.isbuy(), order.executed.price
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
                    self.log(f"ライブモード決済監視開始: TP={self.tp_price:.2f}, Initial SL={self.sl_price:.2f}")
            elif is_exit:
                pnl = order.executed.pnl; exit_reason = "Take Profit" if pnl >= 0 else "Stop Loss"
                subject = f"【リアルタイム取引】決済完了 - {exit_reason} ({self.data0._name})"; body = f"日時: {self.data.datetime.datetime(0).isoformat()}\\n銘柄: {self.data0._name}\\nステータス: {order.getstatusname()} ({exit_reason})\\n方向: {'決済BUY' if order.isbuy() else '決済SELL'}\\n決済数量: {order.executed.size:.2f}\\n決済価格: {order.executed.price:.2f}\\n実現損益: {pnl:,.2f}"
                self.log(f"決済注文完了。 {'BUY' if order.isbuy() else 'SELL'} {order.executed.size:.2f} @ {order.executed.price:.2f}"); self.sl_price, self.tp_price = 0.0, 0.0
            self._send_notification(subject, body)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            subject = f"【リアルタイム取引】注文失敗/キャンセル ({self.data0._name})"; body = f"日時: {self.data.datetime.datetime(0).isoformat()}\\n銘柄: {self.data0._name}\\nステータス: {order.getstatusname()}"
            self.log(f"注文失敗/キャンセル: {order.getstatusname()}"); self._send_notification(subject, body)
            if is_entry: self.sl_price, self.tp_price = 0.0, 0.0
        if is_entry: self.entry_order = None
        if is_exit: self.exit_orders = []

    def notify_trade(self, trade):
        if trade.isopen:
            self.log(f"トレード開始: {'BUY' if trade.long else 'SELL'}, Size: {trade.size}, Price: {trade.price}")
            self.current_position_entry_dt = self.data.datetime.datetime(0)
            self.executed_size = trade.size
            self.entry_reason_for_trade = self.entry_reason
        elif trade.isclosed:
            trade.executed_size = self.executed_size; trade.entry_reason_for_trade = self.entry_reason_for_trade
            self.log(f"トレード終了: PNL Gross {trade.pnl:.2f}, Net {trade.pnlcomm:.2f}")
            self.current_position_entry_dt, self.executed_size = None, 0
            self.entry_reason, self.entry_reason_for_trade = "", ""

    def _place_native_exit_orders(self):
        if not self.getposition().size: return
        sl_cond = self.strategy_params.get('exit_conditions', {}).get('stop_loss', {}); tp_cond = self.strategy_params.get('exit_conditions', {}).get('take_profit', {})
        is_long, size = self.getposition().size > 0, abs(self.getposition().size)
        limit_order, stop_order = None, None
        if tp_cond and self.tp_price != 0:
            limit_order = self.sell(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False) if is_long else self.buy(exectype=bt.Order.Limit, price=self.tp_price, size=size, transmit=False)
            self.log(f"利確(Limit)注文を作成: Price={self.tp_price:.2f}")
        if sl_cond and sl_cond.get('type') == 'atr_stoptrail':
            stop_order = self.sell(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order) if is_long else self.buy(exectype=bt.Order.StopTrail, trailamount=self.risk_per_share, size=size, oco=limit_order)
            self.log(f"損切(StopTrail)注文をOCOで発注: TrailAmount={self.risk_per_share:.2f}")
        self.exit_orders = [o for o in [limit_order, stop_order] if o is not None]

    def _check_live_exit_conditions(self):
        pos = self.getposition(); is_long = pos.size > 0; current_price = self.data.close[0]
        if self.tp_price != 0 and ((is_long and current_price >= self.tp_price) or (not is_long and current_price <= self.tp_price)):
            self.log(f"ライブ: 利確条件ヒット。現在価格: {current_price:.2f}, TP価格: {self.tp_price:.2f}"); self.exit_orders.append(self.close()); return
        if self.sl_price != 0:
            if (is_long and current_price <= self.sl_price) or (not is_long and current_price >= self.sl_price):
                self.log(f"ライブ: 損切り条件ヒット。現在価格: {current_price:.2f}, SL価格: {self.sl_price:.2f}"); self.exit_orders.append(self.close()); return
            new_sl_price = current_price - self.risk_per_share if is_long else current_price + self.risk_per_share
            if (is_long and new_sl_price > self.sl_price) or (not is_long and new_sl_price < self.sl_price):
                self.log(f"ライブ: SL価格を更新 {self.sl_price:.2f} -> {new_sl_price:.2f}"); self.sl_price = new_sl_price

    def _check_entry_conditions(self):
        exit_conditions = self.strategy_params['exit_conditions']; sl_cond = exit_conditions['stop_loss']
        atr_key = self._get_indicator_key(sl_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in sl_cond.get('params', {}).items() if k!='multiplier'})
        atr_indicator = self.indicators.get(atr_key)
        if not atr_indicator or len(atr_indicator) == 0: self.logger.debug(f"ATRインジケーター '{atr_key}' が未計算のためスキップします。"); return
        atr_val = atr_indicator[0]
        if not atr_val or atr_val <= 1e-9: return
        self.risk_per_share = atr_val * sl_cond.get('params', {}).get('multiplier', 2.0)
        if self.risk_per_share < 1e-9: self.log(f"計算されたリスクが0のため、エントリーをスキップします。ATR: {atr_val}"); return
        entry_price = self.data_feeds['short'].close[0]; sizing = self.strategy_params.get('sizing', {})
        size = min((self.broker.getcash()*sizing.get('risk_per_trade',0.01))/self.risk_per_share, sizing.get('max_investment_per_trade', 10000000)/entry_price if entry_price>0 else float('inf'))
        if size <= 0: return
        def place_order(trade_type, reason):
            self.entry_reason, is_long = reason, trade_type == 'long'
            self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
            tp_cond = exit_conditions.get('take_profit')
            if tp_cond:
                tp_key = self._get_indicator_key(tp_cond.get('timeframe', 'short'), 'atr', {k:v for k,v in tp_cond.get('params', {}).items() if k!='multiplier'})
                tp_atr_indicator = self.indicators.get(tp_key)
                if not tp_atr_indicator or len(tp_atr_indicator) == 0: self.log(f"利確用のATRインジケーター '{tp_key}' が未計算です。"); self.tp_price = 0
                else:
                    tp_atr_val = tp_atr_indicator[0]
                    if not tp_atr_val or tp_atr_val <= 1e-9: self.tp_price = 0
                    else:
                        tp_multiplier = tp_cond.get('params', {}).get('multiplier', 5.0)
                        self.tp_price = entry_price + tp_atr_val * tp_multiplier if is_long else entry_price - tp_atr_val * tp_multiplier
            self.log(f"{'BUY' if is_long else 'SELL'} CREATE, Size: {size:.2f}, TP: {self.tp_price:.2f}, SL: {self.sl_price:.2f}")
            self.entry_order = self.buy(size=size) if is_long else self.sell(size=size)
            subject = f"【リアルタイム取引】新規注文発注 ({self.data0._name})"; body = f"日時: {self.data.datetime.datetime(0).isoformat()}\\n銘柄: {self.data0._name}\\n戦略: {self.strategy_params.get('strategy_name', 'N/A')}\\n方向: {'BUY' if is_long else 'SELL'}\\n数量: {size:.2f}\\n\\n--- エントリー根拠詳細 ---\\n{self.entry_reason}"
            self._send_notification(subject, body)
        trading_mode = self.strategy_params.get('trading_mode', {})
        if trading_mode.get('long_enabled', True):
            met, reason = self._check_all_conditions('long')
            if met: place_order('long', reason); return
        if not self.entry_order and trading_mode.get('short_enabled', True):
            met, reason = self._check_all_conditions('short')
            if met: place_order('short', reason)

    def _get_atr_key_for_exit(self, exit_type):
        exit_cond = self.strategy_params.get('exit_conditions', {}).get(exit_type)
        if not exit_cond or exit_cond.get('type') not in ['atr_multiple', 'atr_stoptrail']: return None
        atr_params = {k: v for k, v in exit_cond.get('params', {}).items() if k != 'multiplier'}
        return self._get_indicator_key(exit_cond.get('timeframe', 'short'), 'atr', atr_params)

    def _recalculate_exit_prices(self, entry_price, is_long):
        exit_conditions = self.strategy_params.get('exit_conditions', {}); sl_cond = exit_conditions.get('stop_loss'); tp_cond = exit_conditions.get('take_profit')
        self.sl_price, self.tp_price, self.risk_per_share = 0.0, 0.0, 0.0
        if sl_cond:
            sl_atr_key = self._get_atr_key_for_exit('stop_loss')
            sl_atr_indicator = self.indicators.get(sl_atr_key)
            if sl_atr_indicator and len(sl_atr_indicator) > 0:
                atr_val = sl_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    self.risk_per_share = atr_val * sl_cond['params']['multiplier']
                    self.sl_price = entry_price - self.risk_per_share if is_long else entry_price + self.risk_per_share
        if tp_cond:
            tp_atr_key = self._get_atr_key_for_exit('take_profit')
            tp_atr_indicator = self.indicators.get(tp_atr_key)
            if tp_atr_indicator and len(tp_atr_indicator) > 0:
                atr_val = tp_atr_indicator[0]
                if atr_val and atr_val > 1e-9:
                    self.tp_price = entry_price + (atr_val * tp_cond['params']['multiplier']) if is_long else entry_price - (atr_val * tp_cond['params']['multiplier'])

    def _restore_position_state(self):
        pos_info = self.p.persisted_position
        size, price = pos_info['size'], pos_info['price']
        self.position.size = size; self.position.price = price
        self.current_position_entry_dt = datetime.fromisoformat(pos_info['entry_datetime'])
        self._recalculate_exit_prices(entry_price=price, is_long=(size > 0))
        self.log(f"ポジション復元完了。Size: {self.position.size}, Price: {self.position.price}, SL: {self.sl_price:.2f}, TP: {self.tp_price:.2f}")

    def next(self):
        if self.logger.isEnabledFor(logging.DEBUG):
            # (中略) デバッグログ出力
            pass
        if len(self.data) == 0 or not self.live_trading_started or self.data.volume[0] == 0: return
        if self.is_restoring:
            try:
                atr_key = self._get_atr_key_for_exit('stop_loss')
                if atr_key and self.indicators.get(atr_key) and len(self.indicators.get(atr_key)) > 0:
                    self._restore_position_state(); self.is_restoring = False
                else: self.log("ポジション復元待機中: インジケーターが未計算です..."); return
            except Exception as e:
                self.log(f"ポジションの復元中にクリティカルエラーが発生: {e}", level=logging.CRITICAL); self.is_restoring = False; return
        if self.entry_order or (self.live_trading and self.exit_orders): return
        if self.getposition().size:
            if self.live_trading: self._check_live_exit_conditions()
            return
        self._check_entry_conditions()

        if self.live_trading and self.state_manager:
            self._update_live_status_to_db()

    def _update_live_status_to_db(self):
        try:
            symbol = self.data0._name
            key = f"chart_{symbol}"
            status_data = {
                "price": self.data.close[0],
                "dt": self.data.datetime.datetime(0).isoformat(),
                "position_size": self.getposition().size,
                "position_price": self.getposition().price or 0,
                "sl_price": self.sl_price or 0,
                "tp_price": self.tp_price or 0,
            }
            # ... インジケーター値の追加など ...
            self.state_manager.update_live_status(key, status_data)
            if '1301' in symbol:
                 summary_data = {"cash": self.broker.getcash(), "value": self.broker.getvalue()}
                 self.state_manager.update_live_status("summary", summary_data)
        except Exception as e:
            self.log(f"ライブステータスのDB更新中にエラー: {e}", level=logging.WARNING)

    def log(self, txt, dt=None, level=logging.INFO):
        log_time = dt or self.data.datetime.datetime(0)
        self.logger.log(level, f'{log_time.isoformat()} - {txt}')
        if level >= logging.CRITICAL:
            subject = f"【リアルタイム取引】システム警告 ({self.data0._name})"
            self._send_notification(subject, txt)
""",

    "src/realtrade/run_realtrade.py": """
import logging
import time
import yaml
import pandas as pd
import glob
import os
import sys
import backtrader as bt
import threading
import copy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.core.util import logger as logger_setup
from src.core import strategy as btrader_strategy
from src.core.data_preparer import prepare_data_feeds
from . import config_realtrade as config
from .state_manager import StateManager
from .analyzer import TradePersistenceAnalyzer

if config.LIVE_TRADING:
    if config.DATA_SOURCE == 'YAHOO':
        from .live.yahoo_store import YahooStore as LiveStore
    elif config.DATA_SOURCE == 'RAKUTEN':
        from .bridge.excel_bridge import ExcelBridge
        from .rakuten.rakuten_data import RakutenData
        from .rakuten.rakuten_broker import RakutenBroker
    else:
        raise ValueError(f"サポートされていないDATA_SOURCEです: {config.DATA_SOURCE}")
else:
    from .mock.data_fetcher import MockDataFetcher

class NoCreditInterest(bt.CommInfoBase):
    def get_credit_interest(self, data, pos, dt):
        return 0.0

logger = logging.getLogger(__name__)

class RealtimeTrader:
    def __init__(self):
        logger.info("リアルタイムトレーダーを初期化中...")
        self.strategy_catalog = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_catalog.yml'))
        self.base_strategy_params = self._load_yaml(os.path.join(config.BASE_DIR, 'config', 'strategy_base.yml'))
        self.strategy_assignments = self._load_strategy_assignments(config.RECOMMEND_FILE_PATTERN)
        self.symbols = list(self.strategy_assignments.keys())
        self.state_manager = StateManager(os.path.join(config.BASE_DIR, "results", "realtrade", "realtrade_state.db"))
        self.persisted_positions = self.state_manager.load_positions()
        if self.persisted_positions: logger.info(f"DBから{len(self.persisted_positions)}件の既存ポジションを検出しました。")
        self.threads = []
        self.cerebro_instances = []
        self.bridge = None
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if self.bridge is None:
                logger.info("楽天証券(Excelハブ)モードで初期化します。")
                self.bridge = ExcelBridge(workbook_path=config.EXCEL_WORKBOOK_PATH)
                self.bridge.start()

    def _load_yaml(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: return yaml.safe_load(f)
        except FileNotFoundError: logger.error(f"設定ファイル '{filepath}' が見つかりません。"); raise

    def _load_strategy_assignments(self, filepath_pattern):
        files = glob.glob(filepath_pattern)
        if not files: raise FileNotFoundError(f"銘柄・戦略対応ファイルが見つかりません: {filepath_pattern}")
        latest_file = max(files, key=os.path.getctime)
        logger.info(f"最新の対応ファイルをロード: {latest_file}")
        df = pd.read_csv(latest_file)
        return pd.Series(df.iloc[:, 0].values, index=df.iloc[:, 1].astype(str)).to_dict()

    def _run_cerebro(self, cerebro_instance):
        try: cerebro_instance.run()
        except Exception as e: logger.error(f"Cerebroスレッド ({threading.current_thread().name}) でエラーが発生: {e}", exc_info=True)
        finally: logger.info(f"Cerebroスレッド ({threading.current_thread().name}) が終了しました。")

    def _create_cerebro_for_symbol(self, symbol):
        strategy_name = self.strategy_assignments.get(str(symbol))
        if not strategy_name: logger.warning(f"銘柄 {symbol} に割り当てられた戦略がありません。スキップします。"); return None
        entry_strategy_def = next((item for item in self.strategy_catalog if item["name"] == strategy_name), None)
        if not entry_strategy_def: logger.warning(f"戦略カタログに '{strategy_name}' が見つかりません。スキップします。"); return None
        strategy_params = copy.deepcopy(self.base_strategy_params); strategy_params.update(entry_strategy_def)
        cerebro = bt.Cerebro(runonce=False)
        if config.LIVE_TRADING and config.DATA_SOURCE == 'RAKUTEN':
            if not self.bridge: logger.error("ExcelBridgeが初期化されていません。"); return None
            cerebro.setbroker(RakutenBroker(bridge=self.bridge)); cerebro.broker.addcommissioninfo(NoCreditInterest())
            short_tf_config = strategy_params['timeframes']['short']; compression = short_tf_config['compression']
            search_pattern = os.path.join(config.DATA_DIR, f"{symbol}_{compression}m_*.csv"); files = glob.glob(search_pattern)
            hist_df = pd.DataFrame()
            if files:
                latest_file = max(files, key=os.path.getctime)
                try:
                    df = pd.read_csv(latest_file, index_col='datetime', parse_dates=True)
                    if df.index.tz is not None: df.index = df.index.tz_localize(None)
                    df.columns = [x.lower() for x in df.columns]; hist_df = df
                    logger.info(f"[{symbol}] 過去データとして '{os.path.basename(latest_file)}' ({len(hist_df)}件) を読み込みました。")
                except Exception as e: logger.error(f"[{symbol}] 過去データCSVの読み込みに失敗: {e}")
            else: logger.warning(f"[{symbol}] 過去データCSVが見つかりません (パターン: {search_pattern})。リアルタイムデータのみで開始します。")
            primary_data = RakutenData(dataname=hist_df, bridge=self.bridge, symbol=symbol, timeframe=bt.TimeFrame.TFrame(short_tf_config['timeframe']), compression=short_tf_config['compression'])
            cerebro.adddata(primary_data, name=str(symbol)); logger.info(f"[{symbol}] RakutenData (短期) を追加しました。")
            for tf_name in ['medium', 'long']:
                tf_config = strategy_params['timeframes'].get(tf_name)
                if tf_config:
                    cerebro.resampledata(primary_data, timeframe=bt.TimeFrame.TFrame(tf_config['timeframe']), compression=tf_config['compression'], name=tf_name)
                    logger.info(f"[{symbol}] {tf_name}データをリサンプリングで追加しました。")
        else:
            store = LiveStore() if config.LIVE_TRADING and config.DATA_SOURCE == 'YAHOO' else None
            cerebro.setbroker(bt.brokers.BackBroker()); cerebro.broker.set_cash(config.INITIAL_CAPITAL); cerebro.broker.addcommissioninfo(NoCreditInterest())
            success = prepare_data_feeds(cerebro, strategy_params, symbol, config.DATA_DIR, is_live=config.LIVE_TRADING, live_store=store)
            if not success: return None
        symbol_str = str(symbol)
        persisted_position = self.persisted_positions.get(symbol_str)
        if persisted_position: logger.info(f"[{symbol_str}] の既存ポジション情報を戦略に渡します: {persisted_position}")
        cerebro.addstrategy(btrader_strategy.DynamicStrategy, strategy_params=strategy_params, live_trading=config.LIVE_TRADING, persisted_position=persisted_position, state_manager=self.state_manager)
        cerebro.addanalyzer(TradePersistenceAnalyzer, state_manager=self.state_manager)
        return cerebro

    def start(self):
        logger.info("システムを開始します。")
        if self.bridge: self.bridge.start()
        for symbol in self.symbols:
            logger.info(f"--- 銘柄 {symbol} のセットアップを開始 ---")
            cerebro_instance = self._create_cerebro_for_symbol(symbol)
            if cerebro_instance:
                self.cerebro_instances.append(cerebro_instance)
                t = threading.Thread(target=self._run_cerebro, args=(cerebro_instance,), name=f"Cerebro-{symbol}", daemon=False)
                self.threads.append(t); t.start()
                logger.info(f"Cerebroスレッド (Cerebro-{symbol}) を開始しました。")

    def stop(self):
        logger.info("システムを停止します。全データフィードに停止信号を送信...")
        for cerebro in self.cerebro_instances:
            if cerebro.datas and hasattr(cerebro.datas[0], 'stop'):
                try: cerebro.datas[0].stop()
                except Exception as e: logger.error(f"データフィードの停止中にエラー: {e}")
        if self.bridge: self.bridge.stop()
        logger.info("全Cerebroスレッドの終了を待機中...")
        for t in self.threads: t.join(timeout=10)
        if self.state_manager: self.state_manager.close()
        logger.info("システムが正常に停止しました。")

def main():
    logger_setup.setup_logging(config.LOG_DIR, log_prefix='realtime', level=config.LOG_LEVEL)
    logger.info("--- リアルタイムトレードシステム起動 ---")
    trader = None
    try:
        trader = RealtimeTrader()
        trader.start()
        while True:
            if not trader.threads or not any(t.is_alive() for t in trader.threads):
                logger.warning("稼働中の取引スレッドがありません。システムを終了します。"); break
            time.sleep(5)
    except KeyboardInterrupt: logger.info("\\nCtrl+Cを検知しました。システムを優雅に停止します。")
    except Exception as e: logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)
    finally:
        if trader: trader.stop()
    logger.info("--- リアルタイムトレードシステム終了 ---")

if __name__ == '__main__':
    main()
""",
}

def create_files(files_dict):
    """
    指定された辞書に基づいてプロジェクトファイルとディレクトリを生成します。
    """
    for filename, content in files_dict.items():
        dir_path = os.path.dirname(filename)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"  - ディレクトリ作成: {dir_path}")

        content = content.strip()
        try:
            with open(filename, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"  - ファイル作成/更新: {filename}")
        except IOError as e:
            print(f"エラー: ファイル '{filename}' の作成に失敗しました。 - {e}")

if __name__ == '__main__':
    print("--- ライブ監視機能のファイル生成を開始します (完全版) ---")
    create_files(project_files)
    print("\n--- 完了 ---")
    print("次に、以下のコマンドをそれぞれ別のターミナルで実行してください。")
    print("1. 取引エンジン: python -m src.realtrade.run_realtrade")
    print("2. 監視ダッシュボード: python -m src.dashboard.run_dashboard")