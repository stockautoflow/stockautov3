はい、承知いたしました。  
メール通知機能仕様書 (Ver. 3.0)に基づき、実装を目的とした詳細設計書を作成します。

---

### **メール通知機能 詳細設計書 (Ver. 1.0)**

#### **1\. はじめに**

##### **1.1. 目的**

本ドキュメントは、「メール通知機能仕様書 (Ver. 3.0)」で定義された要件を実現するための、具体的な実装方法、モジュール構成、クラス設計、データ構造、および処理シーケンスを定義する。

##### **1.2. スコープ**

* **対象モジュール:**  
  * src/core/util/notifier.py (大幅な改修)  
  * src/core/strategy.py (一部改修)  
* **新規作成モジュール:**  
  * src/core/util/notification\_logger.py (通知ログ機能)

---

#### **2\. 設計方針**

* **信頼性と監査性の確保:** すべての通知リクエストとその送信結果を永続的なデータベースに記録することで、メール送信の失敗を許容しつつ、完全な監査証跡を確保する。  
* **堅牢なデータ管理:** 複数のスレッドから安全にアクセスするため、また、ステータス更新の原子性を保証するために、通知ログにはCSVファイルではなく**SQLiteデータベース**を採用する。  
* **責務の分離:** メール送信処理（notifier.py）とログ記録処理（notification\_logger.py）の責務を明確に分離し、保守性と拡張性を高める。  
* **コンテキストに応じた動作:** 戦略クラス（strategy.py）が持つ live\_trading フラグを利用し、リアルタイム取引時のみ通知機能が動作するよう制御する。

---

#### **3\. モジュール構成**

コード スニペット

graph TD  
    subgraph strategy.py  
        A\[DynamicStrategy\]  
    end

    subgraph notifier.py  
        B\[send\_email()\]  
        C\[EmailWorkerThread\]  
        D\[PriorityQueue\]  
    end

    subgraph notification\_logger.py  
        E\[NotificationLogger Class\]  
    end

    subgraph Database  
        F\[notification\_history.db\]  
    end

    A \-- 1\. calls \--\> B  
    B \-- 2\. calls \--\> E  
    B \-- 3\. puts item \--\> D  
    C \-- 4\. gets item \--\> D  
    C \-- 5\. sends email \--\> G\[SMTP Server\]  
    C \-- 6\. calls \--\> E  
    E \-- interacts with \--\> F

**処理の流れ:**

1. DynamicStrategyがnotifier.send\_email()を呼び出す。  
2. send\_email()はNotificationLoggerを呼び出し、通知リクエストをDBに記録する。  
3. send\_email()は通知アイテムをPriorityQueueに追加する。  
4. EmailWorkerThreadがキューからアイテムを取り出す。  
5. ワーカースレッドがメール送信を試みる。  
6. ワーカースレッドがNotificationLoggerを再度呼び出し、送信結果をDBに更新する。

---

#### **4\. クラス・関数詳細設計**

##### **4.1. src/core/util/notification\_logger.py (新規作成)**

通知ログ（SQLite）の操作をカプセル化する。

Python

import sqlite3  
import threading  
from datetime import datetime

class NotificationLogger:  
    def \_\_init\_\_(self, db\_path: str):  
        """  
        データベースへの接続とテーブルの初期化を行う。  
        """  
        self.\_db\_path \= db\_path  
        self.\_lock \= threading.Lock() \# スレッドセーフな操作のためのロック  
        self.conn \= sqlite3.connect(db\_path, check\_same\_thread=False)  
        self.\_create\_table()

    def \_create\_table(self):  
        """  
        通知履歴を保存するテーブルを作成する。  
        """  
        with self.\_lock:  
            cursor \= self.conn.cursor()  
            cursor.execute('''  
                CREATE TABLE IF NOT EXISTS notification\_history (  
                    id INTEGER PRIMARY KEY AUTOINCREMENT,  
                    timestamp TEXT NOT NULL,  
                    priority TEXT NOT NULL,  
                    recipient TEXT,  
                    subject TEXT,  
                    body TEXT,  
                    status TEXT NOT NULL,  
                    error\_message TEXT  
                )  
            ''')  
            self.conn.commit()

    def log\_request(self, priority: str, recipient: str, subject: str, body: str) \-\> int:  
        """  
        送信リクエストをDBに記録し、ユニークIDを返す。  
        \- statusは 'PENDING' として記録される。  
        \- 戻り値: 作成されたレコードのID (rowid)  
        """  
        sql \= '''  
            INSERT INTO notification\_history (timestamp, priority, recipient, subject, body, status)  
            VALUES (?, ?, ?, ?, ?, 'PENDING')  
        '''  
        timestamp \= datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')  
        with self.\_lock:  
            cursor \= self.conn.cursor()  
            cursor.execute(sql, (timestamp, priority, recipient, subject, body))  
            self.conn.commit()  
            return cursor.lastrowid

    def update\_status(self, record\_id: int, status: str, error\_message: str \= ""):  
        """  
        指定されたIDのレコードのステータスとエラーメッセージを更新する。  
        \- status: 'SUCCESS' または 'FAILED'  
        """  
        sql \= '''  
            UPDATE notification\_history  
            SET status \= ?, error\_message \= ?  
            WHERE id \= ?  
        '''  
        with self.\_lock:  
            cursor \= self.conn.cursor()  
            cursor.execute(sql, (status, error\_message, record\_id))  
            self.conn.commit()

    def close(self):  
        """  
        データベース接続を閉じる。  
        """  
        if self.conn:  
            self.conn.close()

##### **4.2. src/core/util/notifier.py (改修)**

Python

import queue  
\# ... (他のimport) ...  
from .notification\_logger import NotificationLogger

\# \--- グローバル変数 \---  
\_notification\_queue \= queue.PriorityQueue()  
\_worker\_thread \= None  
\_stop\_event \= threading.Event()  
\_email\_config \= None  
\_logger\_instance \= None \# Loggerインスタンスを保持

\# \--- 主要関数の改修 \---

def start\_notifier():  
    """  
    ワーカースレッドとLoggerを起動する。  
    """  
    global \_worker\_thread, \_logger\_instance  
    if \_logger\_instance is None:  
        \# DBファイルのパスを指定  
        db\_path \= "log/notification\_history.db"  
        \_logger\_instance \= NotificationLogger(db\_path)

    \# ... (ワーカースレッドの起動ロジックは同様) ...

def stop\_notifier():  
    """  
    ワーカースレッドとLoggerを停止する。  
    """  
    \# ... (ワーカースレッドの停止ロジックは同様) ...  
    if \_logger\_instance:  
        \_logger\_instance.close()

def send\_email(subject, body, immediate=False):  
    """  
    通知リクエストをDBに記録し、優先度付きでキューに追加する。  
    """  
    if \_stop\_event.is\_set() or \_logger\_instance is None:  
        return

    priority\_str \= "URGENT" if immediate else "NORMAL"  
    priority\_val \= 0 if immediate else 1

    try:  
        \# 1\. 通知リクエストをDBに記録し、レコードIDを取得  
        record\_id \= \_logger\_instance.log\_request(  
            priority=priority\_str,  
            recipient=\_email\_config.get("RECIPIENT\_EMAIL", ""),  
            subject=subject,  
            body=body  
        )

        \# 2\. キューにアイテムを追加 (レコードIDも渡す)  
        item \= {  
            'record\_id': record\_id,  
            'subject': subject,  
            'body': body  
        }  
        \_notification\_queue.put((priority\_val, item))

    except Exception as e:  
        logger.error(f"通知リクエストのロギングまたはキューイングに失敗: {e}")

def \_email\_worker():  
    """  
    メール送信と結果のロギングを行うワーカースレッド。  
    """  
    while not \_stop\_event.is\_set():  
        try:  
            priority, item \= \_notification\_queue.get(timeout=1)  
            record\_id \= item\['record\_id'\]

            server \= \_get\_server()  
            if not server:  
                \_logger\_instance.update\_status(record\_id, "FAILED", "SMTP Server not available")  
                continue

            \# ... (MIMEText作成など) ...

            try:  
                \# 3\. メール送信試行  
                server.send\_message(msg)  
                \# 4\. 成功結果をDBに更新  
                \_logger\_instance.update\_status(record\_id, "SUCCESS")  
                logger.info("メールを正常に送信しました。")  
            except Exception as e:  
                \# 5\. 失敗結果をDBに更新  
                \_logger\_instance.update\_status(record\_id, "FAILED", str(e))  
                logger.critical(f"メール送信中にエラー: {e}", exc\_info=True)  
                \# ... (サーバー再接続ロジックなど) ...

            \# 6\. 優先度に応じた待機  
            time.sleep(0.1 if priority \== 0 else 2.0)

        except queue.Empty:  
            continue

##### **4.3. src/core/strategy.py (改修)**

\_send\_notificationメソッドが、リアルタイム取引時のみnotifierを呼び出すようにする。

Python

def \_send\_notification(self, subject, body, immediate=False):  
    """  
    リアルタイム取引時のみ、通知リクエストを送信する。  
    """  
    \# バックテスト時はメール通知機能を完全に無効化  
    if not self.live\_trading:  
        return

    self.logger.debug(f"通知リクエストを発行: {subject} (Immediate: {immediate})")  
    notifier.send\_email(subject, body, immediate=immediate)

---

#### **5\. データ構造**

##### **5.1. notification\_history.db テーブルスキーマ**

SQL

CREATE TABLE IF NOT EXISTS notification\_history (  
    id INTEGER PRIMARY KEY AUTOINCREMENT, \-- レコードを一意に識別するID  
    timestamp TEXT NOT NULL,              \-- 'YYYY-MM-DD HH:MM:SS.ffffff' 形式  
    priority TEXT NOT NULL,               \-- 'URGENT' または 'NORMAL'  
    recipient TEXT,                       \-- 送信先メールアドレス  
    subject TEXT,                         \-- メールの件名  
    body TEXT,                            \-- メールの本文  
    status TEXT NOT NULL,                 \-- 'PENDING', 'SUCCESS', 'FAILED'  
    error\_message TEXT                    \-- 送信失敗時のエラーメッセージ  
);  
