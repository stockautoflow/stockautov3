from flask import Flask, jsonify, render_template
from .data_provider import DataProvider
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(db_path):
    """
    Flaskアプリケーションを生成するファクトリ関数。
    """
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