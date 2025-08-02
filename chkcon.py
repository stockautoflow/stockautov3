import socket
import smtplib

# --- チェックするサーバー情報 ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

print(f"--- 接続診断を開始します ---")
print(f"サーバー: {SMTP_SERVER}, ポート: {SMTP_PORT}\\n")

# --- ステップ1: DNS解決のテスト ---
print("ステップ1: DNSサーバーへの名前解決をテスト中...")
try:
    ip_address = socket.gethostbyname(SMTP_SERVER)
    print(f"  [成功] {SMTP_SERVER} のIPアドレスを正常に取得しました: {ip_address}")
except socket.gaierror as e:
    print(f"  [失敗] DNSの名前解決に失敗しました。")
    print(f"   エラー詳細: {e}")
    print("\\n結論: ネットワークのDNS設定に問題があるか、プロキシ環境などが原因である可能性が高いです。")
    exit()
except Exception as e:
    print(f"  [失敗] 予期せぬエラーが発生しました。")
    print(f"   エラー詳細: {e}")
    exit()

# --- ステップ2: サーバーへの接続テスト ---
print("\\nステップ2: SMTPサーバーへの接続をテスト中...")
try:
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
        server.set_debuglevel(1)  # 詳細なログを出力
        print("\\n  [成功] サーバーへの初期接続に成功しました。")
        # ehlo()を呼び出して接続を確立
        server.ehlo()
        # starttls()で暗号化を開始
        server.starttls()
        print("  [成功] TLS暗号化通信の開始にも成功しました。")

except smtplib.SMTPConnectError as e:
    print(f"  [失敗] サーバーへの接続が拒否されました。")
    print(f"   エラー詳細: {e}")
    print("\\n結論: ファイアウォールやセキュリティソフトがポート587の通信をブロックしている可能性が高いです。")
except socket.timeout:
    print(f"  [失敗] サーバーへの接続がタイムアウトしました。")
    print("\\n結論: ネットワーク経路のどこかで通信がブロックされているか、サーバーが応答していません。")
except Exception as e:
    print(f"  [失敗] 予期せぬエラーが発生しました。")
    print(f"   エラー詳細: {e}")

print("\\n--- 診断を終了します ---")