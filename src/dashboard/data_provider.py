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