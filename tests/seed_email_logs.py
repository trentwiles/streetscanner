"""
Seed sample email_queue and logs entries for dashboard testing.
Run from project root: python tests/seed_email_logs.py
"""

import sqlite3
import os
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "streetscanner.db")


def seed(con):
    now = datetime.now(timezone.utc)

    # Grab existing job IDs
    jobs = con.execute("SELECT request_id, email FROM jobs").fetchall()
    if not jobs:
        print("No jobs found — run seed_jobs.py first.")
        return

    # Email queue entries
    emails = [
        {
            "request_id": jobs[0]["request_id"],
            "email": jobs[0]["email"],
            "subject": f"Bus prices: New York → Boston | {now.strftime('%b %-d')} – {(now + timedelta(days=28)).strftime('%b %-d')}",
            "html_body": "<html><body><h1>New York → Boston</h1><p>Cheapest fare: <strong>$12</strong> on Friday via Peter Pan.</p></body></html>",
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "sent_at": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "request_id": jobs[1]["request_id"] if len(jobs) > 1 else jobs[0]["request_id"],
            "email": jobs[1]["email"] if len(jobs) > 1 else jobs[0]["email"],
            "subject": f"Bus prices: Boston → New York | {now.strftime('%b %-d')} – {(now + timedelta(days=28)).strftime('%b %-d')}",
            "html_body": "<html><body><h1>Boston → New York</h1><p>Cheapest fare: <strong>$15</strong> on Sunday via Greyhound.</p></body></html>",
            "created_at": (now - timedelta(minutes=30)).isoformat(),
            "sent_at": None,
        },
        {
            "request_id": jobs[0]["request_id"],
            "email": "pending@example.com",
            "subject": "Bus prices: New York → Washington | May 2 – May 30",
            "html_body": "<html><body><h1>New York → Washington</h1><p>No results found for the requested dates.</p></body></html>",
            "created_at": now.isoformat(),
            "sent_at": None,
        },
    ]

    for e in emails:
        con.execute(
            "INSERT OR IGNORE INTO email_queue (request_id, email, subject, html_body, created_at, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (e["request_id"], e["email"], e["subject"], e["html_body"], e["created_at"], e["sent_at"]),
        )

    # Log entries
    logs = [
        ("error", "greyhound", jobs[0]["request_id"], "got a non-200 from upstream (HTTP 503)"),
        ("warning", "ourbus", jobs[0]["request_id"], "no route translations found for this city pair"),
        ("info", None, None, "job fulfillment started"),
        ("info", "peterpan", jobs[0]["request_id"], "found 3 trips for 2026-05-03"),
        ("error", "coachrun", jobs[1]["request_id"] if len(jobs) > 1 else jobs[0]["request_id"], "connection timeout after 30s"),
        ("info", "greyhound", jobs[1]["request_id"] if len(jobs) > 1 else jobs[0]["request_id"], "found 1 trip for 2026-05-05"),
        ("warning", "peterpan", None, "rate limit warning: 429 received, backing off"),
        ("info", None, None, "job fulfillment completed: 2 jobs processed"),
    ]

    base_time = now - timedelta(hours=1)
    for i, (level, company, rid, message) in enumerate(logs):
        ts = (base_time + timedelta(minutes=i * 7)).isoformat()
        con.execute(
            "INSERT INTO logs (created_at, level, company, request_id, message) VALUES (?, ?, ?, ?, ?)",
            (ts, level, company, rid, message),
        )

    con.commit()
    print(f"Seeded {len(emails)} emails, {len(logs)} log entries")


if __name__ == "__main__":
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    seed(con)
    con.close()
