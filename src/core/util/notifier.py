import smtplib
import yaml
import logging
import socket
import queue
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

_notification_queue = queue.Queue()
_worker_thread = None
_stop_event = threading.Event()
_smtp_server = None
_email_config = None

def _get_server():
    global _smtp_server, _email_config

    if _email_config is None:
        _email_config = load_email_config()

    if not _email_config.get("ENABLED"):
        return None

    if _smtp_server:
        try:
            status = _smtp_server.noop()
            if status[0] == 250:
                return _smtp_server
        except smtplib.SMTPServerDisconnected:
            logger.warning("SMTPサーバーとの接続が切断されました。再接続します。")
            _smtp_server = None

    try:
        server_name = _email_config["SMTP_SERVER"]
        server_port = _email_config["SMTP_PORT"]
        logger.info(f"SMTPサーバーに新規接続します: {server_name}:{server_port}")
        
        server = smtplib.SMTP(server_name, server_port, timeout=20)
        server.starttls()
        server.login(_email_config["SMTP_USER"], _email_config["SMTP_PASSWORD"])
        
        _smtp_server = server
        return _smtp_server
    except Exception as e:
        logger.critical(f"SMTPサーバーへの接続またはログインに失敗しました: {e}", exc_info=True)
        return None

def _email_worker():
    while not _stop_event.is_set():
        try:
            item = _notification_queue.get(timeout=1)
            if item is None: # 停止シグナル
                break

            server = _get_server()
            if not server:
                continue

            msg = MIMEMultipart()
            msg['From'] = _email_config["SMTP_USER"]
            msg['To'] = _email_config["RECIPIENT_EMAIL"]
            msg['Subject'] = item['subject']
            msg.attach(MIMEText(item['body'], 'plain', 'utf-8'))

            try:
                logger.info(f"メールを送信中... To: {_email_config['RECIPIENT_EMAIL']}")
                server.send_message(msg)
                logger.info("メールを正常に送信しました。")
            except Exception as e:
                logger.critical(f"メール送信中に予期せぬエラーが発生しました: {e}", exc_info=True)
                global _smtp_server
                _smtp_server = None
            
            time.sleep(2) # 2秒待機

        except queue.Empty:
            continue

def start_notifier():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_email_worker, daemon=True)
        _worker_thread.start()
        logger.info("メール通知ワーカースレッドを開始しました。")

def stop_notifier():
    global _worker_thread, _smtp_server
    if _worker_thread and _worker_thread.is_alive():
        logger.info("メール通知ワーカースレッドを停止します...")
        _notification_queue.put(None) # 停止シグナルをキューに追加
        _worker_thread.join(timeout=10)
        if _worker_thread.is_alive():
            logger.warning("ワーカースレッドがタイムアウト後も終了していません。")
    
    if _smtp_server:
        logger.info("SMTPサーバーとの接続を閉じます。")
        _smtp_server.quit()
        _smtp_server = None
    
    _worker_thread = None
    logger.info("メール通知システムが正常に停止しました。")


def load_email_config():
    global _email_config
    if _email_config is not None:
        return _email_config
    try:
        with open('config/email_config.yml', 'r', encoding='utf-8') as f:
            _email_config = yaml.safe_load(f)
            return _email_config
    except FileNotFoundError:
        logger.warning("config/email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"config/email_config.ymlの読み込み中にエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body):
    _notification_queue.put({'subject': subject, 'body': body})