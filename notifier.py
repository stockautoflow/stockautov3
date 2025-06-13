import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config_backtrader as config

def send_email(subject, body):
    if not config.EMAIL_CONFIG["ENABLED"]:
        return

    msg = MIMEMultipart()
    msg['From'] = config.EMAIL_CONFIG["SMTP_USER"]
    msg['To'] = config.EMAIL_CONFIG["RECIPIENT_EMAIL"]
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        print(f"メールを送信中... To: {config.EMAIL_CONFIG['RECIPIENT_EMAIL']}")
        server = smtplib.SMTP(config.EMAIL_CONFIG["SMTP_SERVER"], config.EMAIL_CONFIG["SMTP_PORT"])
        server.starttls()
        server.login(config.EMAIL_CONFIG["SMTP_USER"], config.EMAIL_CONFIG["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        print("メールを正常に送信しました。")
    except Exception as e:
        print(f"メール送信中にエラーが発生しました: {e}")
