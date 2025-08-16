import smtplib
import yaml
import logging
import queue
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .notification_logger import NotificationLogger

logger = logging.getLogger(__name__)

# --- グローバル変数 ---
_notification_queue = queue.PriorityQueue()
_worker_thread = None
_stop_event = threading.Event()
_smtp_server = None
_email_config = None
_logger_instance = None

def _get_server():
    global _smtp_server, _email_config
    if _email_config is None: _email_config = load_email_config()
    if not _email_config.get("ENABLED"): return None
    if _smtp_server:
        try:
            if _smtp_server.noop()[0] == 250: return _smtp_server
        except smtplib.SMTPServerDisconnected:
            logger.warning("SMTPサーバーとの接続が切断されました。再接続します。")
            _smtp_server = None
    try:
        server_name, server_port = _email_config["SMTP_SERVER"], _email_config["SMTP_PORT"]
        logger.info(f"SMTPサーバーに新規接続します: {server_name}:{server_port}")
        server = smtplib.SMTP(server_name, server_port, timeout=20)
        server.starttls()
        server.login(_email_config["SMTP_USER"], _email_config["SMTP_PASSWORD"])
        _smtp_server = server
        return _smtp_server
    except Exception as e:
        logger.critical(f"SMTPサーバーへの接続/ログイン失敗: {e}", exc_info=True)
        return None

def _email_worker():
    while not _stop_event.is_set():
        try:
            # <<< 変更点 1/3: タイムスタンプも受け取るようにアンパック処理を変更
            priority, timestamp, item = _notification_queue.get(timeout=1)
            if item is None: break

            record_id = item['record_id']
            server = _get_server()
            if not server:
                if _logger_instance:
                    _logger_instance.update_status(record_id, "FAILED", "SMTP Server not available")
                continue
            
            msg = MIMEMultipart()
            msg['From'] = _email_config["SMTP_USER"]
            msg['To'] = _email_config["RECIPIENT_EMAIL"]
            msg['Subject'] = item['subject']
            msg.attach(MIMEText(item['body'], 'plain', 'utf-8'))

            try:
                logger.info(f"メールを送信中... To: {_email_config['RECIPIENT_EMAIL']}")
                server.send_message(msg)
                if _logger_instance: _logger_instance.update_status(record_id, "SUCCESS")
                logger.info("メールを正常に送信しました。")
            except Exception as e:
                if _logger_instance: _logger_instance.update_status(record_id, "FAILED", str(e))
                logger.critical(f"メール送信中にエラー: {e}", exc_info=True)
                global _smtp_server
                _smtp_server = None
            
            time.sleep(0.1 if priority == 0 else 2.0)
        except queue.Empty:
            continue

def start_notifier():
    global _worker_thread, _logger_instance
    if _logger_instance is None:
        db_path = "log/notification_history.db"
        _logger_instance = NotificationLogger(db_path)
        logger.info(f"通知ロガーを初期化しました。DB: {db_path}")
    if _worker_thread is None or not _worker_thread.is_alive():
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_email_worker, daemon=True)
        _worker_thread.start()
        logger.info("メール通知ワーカースレッドを開始しました。")

def stop_notifier():
    global _worker_thread, _smtp_server, _logger_instance
    if _worker_thread and _worker_thread.is_alive():
        logger.info("メール通知ワーカースレッドを停止します...")
        # <<< 変更点 2/3: 停止シグナルの形式をタプルに合わせる
        _notification_queue.put((-1, time.time(), None))
        _worker_thread.join(timeout=10)
    if _smtp_server:
        _smtp_server.quit()
        _smtp_server = None
        logger.info("SMTPサーバーとの接続を閉じました。")
    if _logger_instance:
        _logger_instance.close()
        logger.info("通知ロガーの接続を閉じました。")
    _worker_thread = None
    logger.info("メール通知システムが正常に停止しました。")

def load_email_config():
    global _email_config
    if _email_config is not None: return _email_config
    try:
        with open('config/email_config.yml', 'r', encoding='utf-8') as f:
            _email_config = yaml.safe_load(f)
            return _email_config
    except FileNotFoundError:
        logger.warning("config/email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"config/email_config.ymlの読み込みエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body, immediate=False):
    config = load_email_config()
    if not config.get("ENABLED") or _stop_event.is_set() or _logger_instance is None:
        return

    priority_str = "URGENT" if immediate else "NORMAL"
    priority_val = 0 if immediate else 1

    try:
        record_id = _logger_instance.log_request(
            priority=priority_str,
            recipient=config.get("RECIPIENT_EMAIL", ""),
            subject=subject,
            body=body
        )
        
        # <<< 変更点 3/3: タイムスタンプをキューのタプルに追加
        timestamp = time.time()
        item = {'record_id': record_id, 'subject': subject, 'body': body}
        _notification_queue.put((priority_val, timestamp, item))

    except Exception as e:
        logger.error(f"通知リクエストのロギング/キューイング失敗: {e}", exc_info=True)