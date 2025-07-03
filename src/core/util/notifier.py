import smtplib
import yaml
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

def load_email_config():
    """
    設定ファイルからメール設定を読み込みます。
    [リファクタリング] パスを'config/email_config.yml'に修正。
    """
    try:
        with open('config/email_config.yml', 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("config/email_config.ymlが見つかりません。メール通知は無効になります。")
        return {"ENABLED": False}
    except Exception as e:
        logger.error(f"config/email_config.ymlの読み込み中にエラー: {e}")
        return {"ENABLED": False}

def send_email(subject, body):
    """
    設定に基づいてメールを送信します。
    """
    email_config = load_email_config()
    if not email_config.get("ENABLED"):
        return
        
    msg = MIMEMultipart()
    msg['From'] = email_config["SMTP_USER"]
    msg['To'] = email_config["RECIPIENT_EMAIL"]
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    try:
        logger.info(f"メールを送信中... To: {email_config['RECIPIENT_EMAIL']}")
        server = smtplib.SMTP(email_config["SMTP_SERVER"], email_config["SMTP_PORT"])
        server.starttls()
        server.login(email_config["SMTP_USER"], email_config["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        logger.info("メールを正常に送信しました。")
    except Exception as e:
        logger.error(f"メール送信中にエラーが発生しました: {e}")