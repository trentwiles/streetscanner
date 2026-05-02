"""
mailer.py — drain the email_queue table and send via SMTP.

Rows with sent_at IS NULL are pending. On success the row is stamped with
sent_at; on failure it is left pending so the next run retries it.

Configuration (environment variables):
  SMTP_HOST   default: localhost
  SMTP_PORT   default: 25
  SMTP_FROM   default: streetscanner@localhost
  SMTP_USER   optional — if set, login is attempted with SMTP_PASS
  SMTP_PASS   optional
"""

import os
import smtplib

from dotenv import load_dotenv
load_dotenv()
import sqlite3
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

DB_PATH = "streetscanner.db"

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
SMTP_FROM = os.getenv("SMTP_FROM", "streetscanner@localhost")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


def _build_message(to: str, subject: str, html_body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    return msg


def _send(to: str, subject: str, html_body: str) -> None:
    msg = _build_message(to, subject, html_body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASS or "")
        smtp.sendmail(SMTP_FROM, [to], msg.as_string())


def drain_queue() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    pending = con.execute(
        "SELECT * FROM email_queue WHERE sent_at IS NULL ORDER BY id"
    ).fetchall()

    if not pending:
        print("No pending emails.")
        con.close()
        return

    print(f"{len(pending)} pending email(s).")

    for row in pending:
        to = row["email"]
        subject = row["subject"]
        try:
            _send(to, subject, row["html_body"])
            sent_at = datetime.now(timezone.utc).isoformat()
            con.execute(
                "UPDATE email_queue SET sent_at = ? WHERE id = ?",
                (sent_at, row["id"]),
            )
            con.commit()
            print(f"  [SENT]   #{row['id']} → {to} | {subject}")
        except Exception as e:
            print(f"  [FAILED] #{row['id']} → {to} | {e}")

    con.close()


if __name__ == "__main__":
    drain_queue()
