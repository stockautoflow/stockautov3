import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# --- 正規表現 ---
SUBJECT_RE = re.compile(r"【RT】(.+?)(?: - (Take Profit|Stop Loss))? \((\d{4,})\)")
BODY_PATTERNS = {
    'direction': re.compile(r"方向: (BUY|SELL)"), 'quantity': re.compile(r"数量: ([\d.]+)"), 'price': re.compile(r"価格: ([\d.]+)"),
    'tp': re.compile(r"TP: ([\d.]+)"), 'sl': re.compile(r"SL: ([\d.]+)"), 'reason': re.compile(r"--- エントリー根拠 ---\n(.*)", re.DOTALL),
    'exec_price': re.compile(r"約定価格: ([\d.]+)"), 'pnl': re.compile(r"実現損益: ([\-+,.\d]+)"), 'status': re.compile(r"ステータス: (\w+)"),
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
            
    return result