from email.mime.multipart import MIMEMultipart
import config_backtrader as config
import logging

logger = logging.getLogger(__name__)

def send_email(subject, body):
    if not config.EMAIL_CONFIG["ENABLED"]:
        return

    msg = MIMEMultipart()
    msg['From'] = config.EMAIL_CONFIG["SMTP_USER"]
    msg['To'] = config.EMAIL_CONFIG["RECIPIENT_EMAIL"]
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        logger.info(f"メールを送信中... To: {config.EMAIL_CONFIG['RECIPIENT_EMAIL']}")
        server = smtplib.SMTP(config.EMAIL_CONFIG["SMTP_SERVER"], config.EMAIL_CONFIG["SMTP_PORT"])
        server.starttls()
        server.login(config.EMAIL_CONFIG["SMTP_USER"], config.EMAIL_CONFIG["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        logger.info("メールを正常に送信しました。")
    except Exception as e:
        logger.error(f"メール送信中にエラーが発生しました: {e}")

