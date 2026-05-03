"""
mailer.py — send one pending email from email_queue, if within the send window.

Intended to be run by cron every 20 minutes. Each invocation:
  1. Checks the current local time is within SEND_WINDOW_START–SEND_WINDOW_END.
  2. Picks the oldest unsent row and sends it.
  3. Stamps sent_at on success; leaves the row for retry on failure.

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
from datetime import datetime, timezone, time as dt_time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SEND_WINDOW_START = dt_time(5, 30)
SEND_WINDOW_END   = dt_time(8, 0)

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


def within_send_window() -> bool:
    now = datetime.now().time()
    return SEND_WINDOW_START <= now <= SEND_WINDOW_END


def send_one() -> None:
    now = datetime.now().time()
    if not within_send_window():
        print(f"Outside send window ({SEND_WINDOW_START}–{SEND_WINDOW_END}), current time {now}. Exiting.")
        return

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    row = con.execute(
        "SELECT * FROM email_queue WHERE sent_at IS NULL ORDER BY id LIMIT 1"
    ).fetchone()

    if not row:
        print("No pending emails.")
        con.close()
        return

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
        print(f"[SENT] #{row['id']} → {to} | {subject}")
    except Exception as e:
        print(f"[FAILED] #{row['id']} → {to} | {e}")

    con.close()


if __name__ == "__main__":
    send_one()
