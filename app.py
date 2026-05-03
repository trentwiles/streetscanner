"""
app.py — Flask API server for StreetScanner.

Serves:
  - Static React frontend (built into frontend/dist)
  - /api/* — JSON REST API
  - /auth/* — GitHub OAuth flow
"""

import os
import smtplib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

# Allow OAuth over plain HTTP in local dev
if os.getenv("OAUTHLIB_INSECURE_TRANSPORT"):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from flask import Flask, jsonify, request, session, redirect, url_for, send_from_directory, abort, render_template_string
from flask_dance.contrib.github import make_github_blueprint, github

DB_PATH = os.path.join(os.path.dirname(__file__), "streetscanner.db")

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5001")
VERIFICATION_TTL_HOURS = 24

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
SMTP_FROM = os.getenv("SMTP_FROM", "streetscanner@localhost")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


def _send_email(to: str, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASS or "")
        smtp.sendmail(SMTP_FROM, [to], msg.as_string())


app = Flask(__name__, static_folder="frontend/dist", static_url_path="")

app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

# ── GitHub OAuth ──────────────────────────────────────────────────────────────

github_bp = make_github_blueprint(
    client_id=os.getenv("GITHUB_CLIENT_ID", ""),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
    redirect_url="/auth/callback",
)
app.register_blueprint(github_bp, url_prefix="/auth/github")


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def ensure_tables():
    """Create any missing tables (idempotent)."""
    con = get_db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS cities (
            id   TEXT PRIMARY KEY,
            city TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS translations (
            bus_company TEXT NOT NULL,
            identifier  TEXT NOT NULL,
            city_id     TEXT NOT NULL REFERENCES cities(id),
            PRIMARY KEY (bus_company, city_id)
        );
        CREATE TABLE IF NOT EXISTS jobs (
            request_id        TEXT PRIMARY KEY,
            email             TEXT NOT NULL,
            submit_ip         TEXT,
            submit_time       TEXT,
            submit_user_agent TEXT,
            originCity        TEXT NOT NULL,
            destCity          TEXT NOT NULL,
            days              TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS email_queue (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT REFERENCES jobs(request_id),
            email      TEXT NOT NULL,
            subject    TEXT NOT NULL,
            html_body  TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            level      TEXT NOT NULL,
            company    TEXT,
            request_id TEXT REFERENCES jobs(request_id),
            message    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending_verifications (
            token             TEXT PRIMARY KEY,
            email             TEXT NOT NULL,
            origin_city_id    TEXT NOT NULL,
            dest_city_id      TEXT NOT NULL,
            days              TEXT NOT NULL,
            submit_ip         TEXT,
            submit_user_agent TEXT,
            created_at        TEXT NOT NULL
        );
    """)
    con.commit()
    con.close()


# ── Auth helpers ──────────────────────────────────────────────────────────────

ALLOWED_USERS = [u.strip() for u in os.getenv("GITHUB_ALLOWED_USERS", "trentwiles").split(",") if u.strip()]


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("github_login"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/auth/login")
def auth_login():
    """Redirect to GitHub OAuth."""
    return redirect(url_for("github.login"))


@app.route("/auth/callback")
def auth_callback():
    if not github.authorized:
        return redirect(url_for("auth_login") + "?error=unauthorized")
    resp = github.get("/user")
    if not resp.ok:
        return redirect(url_for("auth_login") + "?error=unauthorized")
    login = resp.json().get("login", "")
    if login not in ALLOWED_USERS:
        return redirect(url_for("auth_login") + "?error=unauthorized")
    session["github_login"] = login
    # In dev, Vite runs on 5173; in production the SPA is served by Flask itself.
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "")
    return redirect(f"{frontend_origin}/admin")


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/auth/me")
def auth_me():
    login = session.get("github_login")
    if login:
        return jsonify({"login": login})
    return jsonify({"error": "not authenticated"}), 401


# ── API: cities ───────────────────────────────────────────────────────────────

@app.route("/api/cities")
def api_cities():
    con = get_db()
    rows = con.execute("SELECT id, city FROM cities ORDER BY city").fetchall()
    con.close()
    return jsonify({"cities": [{"id": r["id"], "name": r["city"]} for r in rows]})


# ── API: jobs ─────────────────────────────────────────────────────────────────

@app.route("/api/jobs", methods=["POST"])
def api_submit_job():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    origin_city = data.get("origin_city", "").strip()
    dest_city = data.get("dest_city", "").strip()
    days = data.get("days", [])

    if not email or not origin_city or not dest_city or not days:
        return jsonify({"error": "email, origin_city, dest_city, and days are required"}), 400

    if not isinstance(days, list) or not all(isinstance(d, str) for d in days):
        return jsonify({"error": "days must be a list of strings"}), 400

    valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    if not all(d in valid_days for d in days):
        return jsonify({"error": "invalid day abbreviation"}), 400

    con = get_db()
    origin_row = con.execute("SELECT city FROM cities WHERE id = ?", (origin_city,)).fetchone()
    dest_row = con.execute("SELECT city FROM cities WHERE id = ?", (dest_city,)).fetchone()
    if not origin_row or not dest_row:
        con.close()
        return jsonify({"error": "unknown city id"}), 422

    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        """INSERT INTO pending_verifications
               (token, email, origin_city_id, dest_city_id, days, submit_ip, submit_user_agent, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (token, email, origin_city, dest_city, ",".join(days),
         request.remote_addr, request.headers.get("User-Agent"), now),
    )
    con.commit()
    con.close()

    verify_url = f"{APP_BASE_URL}/api/verify/{token}"
    with open(os.path.join(app.root_path, "templates", "verify_email.html")) as f:
        tmpl = f.read()
    html_body = render_template_string(tmpl, verify_url=verify_url,
                                       origin=origin_row["city"], dest=dest_row["city"],
                                       ttl_hours=VERIFICATION_TTL_HOURS)
    try:
        _send_email(email, "Confirm your StreetScanner subscription", html_body)
    except Exception as e:
        return jsonify({"error": f"failed to send verification email: {e}"}), 502

    return jsonify({"pending": True}), 202


@app.route("/api/jobs", methods=["GET"])
@require_auth
def api_list_jobs():
    page = max(1, int(request.args.get("page", 1)))
    limit = max(1, min(100, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit
    con = get_db()
    total = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    rows = con.execute(
        "SELECT request_id, email, originCity, destCity, days, submit_time, submit_ip, submit_user_agent FROM jobs ORDER BY submit_time DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    con.close()
    jobs = [
        {
            "request_id": r["request_id"],
            "email": r["email"],
            "origin_city": r["originCity"],
            "dest_city": r["destCity"],
            "days": r["days"].split(",") if r["days"] else [],
            "submit_time": r["submit_time"],
            "submit_ip": r["submit_ip"],
            "submit_user_agent": r["submit_user_agent"],
        }
        for r in rows
    ]
    return jsonify({"jobs": jobs, "total": total, "page": page, "limit": limit})


@app.route("/api/verify/<token>")
def api_verify_email(token):
    con = get_db()
    row = con.execute("SELECT * FROM pending_verifications WHERE token = ?", (token,)).fetchone()
    if not row:
        con.close()
        return _verification_page("Invalid or already-used link.",
                                  "This confirmation link is not valid or has already been used.", success=False), 400

    created = datetime.fromisoformat(row["created_at"])
    if datetime.now(timezone.utc) - created > timedelta(hours=VERIFICATION_TTL_HOURS):
        con.execute("DELETE FROM pending_verifications WHERE token = ?", (token,))
        con.commit()
        con.close()
        return _verification_page("Link expired.",
                                  f"This confirmation link expired after {VERIFICATION_TTL_HOURS} hours. Please submit the form again.", success=False), 410

    origin_row = con.execute("SELECT city FROM cities WHERE id = ?", (row["origin_city_id"],)).fetchone()
    dest_row = con.execute("SELECT city FROM cities WHERE id = ?", (row["dest_city_id"],)).fetchone()
    if not origin_row or not dest_row:
        con.close()
        return _verification_page("Error.", "An internal error occurred. Please try again.", success=False), 500

    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        """INSERT INTO jobs (request_id, email, submit_ip, submit_time, submit_user_agent, originCity, destCity, days)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (request_id, row["email"], row["submit_ip"], now,
         row["submit_user_agent"], origin_row["city"], dest_row["city"], row["days"]),
    )
    con.execute("DELETE FROM pending_verifications WHERE token = ?", (token,))
    con.commit()
    con.close()
    return _verification_page("You're subscribed!",
                              f"Your email has been confirmed. We'll send bus price updates for {origin_row['city']} → {dest_row['city']} to {row['email']}.", success=True)


def _verification_page(title: str, message: str, success: bool) -> str:
    color = "#1a7a4a" if success else "#c0392b"
    icon = "✓" if success else "✗"
    return render_template_string("""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }} — StreetScanner</title>
  <style>
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
    .card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 40px 48px; max-width: 480px; width: 90%; text-align: center; }
    .icon { font-size: 48px; color: {{ color }}; }
    h1 { font-size: 22px; color: #222; margin: 12px 0 8px; }
    p { color: #555; line-height: 1.5; margin: 0 0 24px; }
    a { display: inline-block; background: #1a1a2e; color: #fff; text-decoration: none; padding: 10px 24px; border-radius: 5px; font-size: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{{ icon }}</div>
    <h1>{{ title }}</h1>
    <p>{{ message }}</p>
    <a href="/">Back to StreetScanner</a>
  </div>
</body>
</html>""", title=title, message=message, color=color, icon=icon)


@app.route("/api/jobs/<request_id>", methods=["DELETE"])
@require_auth
def api_delete_job(request_id):
    con = get_db()
    result = con.execute("DELETE FROM jobs WHERE request_id = ?", (request_id,))
    con.commit()
    con.close()
    if result.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    return "", 204


# ── API: email queue ──────────────────────────────────────────────────────────

@app.route("/api/email-queue")
@require_auth
def api_email_queue():
    status = request.args.get("status", "all")
    page = max(1, int(request.args.get("page", 1)))
    limit = max(1, min(100, int(request.args.get("limit", 20))))
    offset = (page - 1) * limit

    if status == "pending":
        where_clause = "WHERE sent_at IS NULL"
    elif status == "sent":
        where_clause = "WHERE sent_at IS NOT NULL"
    else:
        where_clause = ""

    con = get_db()
    total = con.execute(f"SELECT COUNT(*) FROM email_queue {where_clause}").fetchone()[0]
    rows = con.execute(
        f"SELECT id, request_id, email, subject, created_at, sent_at FROM email_queue {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    con.close()
    emails = [
        {
            "id": r["id"],
            "request_id": r["request_id"],
            "email": r["email"],
            "subject": r["subject"],
            "created_at": r["created_at"],
            "sent_at": r["sent_at"],
        }
        for r in rows
    ]
    return jsonify({"emails": emails, "total": total, "page": page, "limit": limit})


@app.route("/api/email-queue/<int:email_id>/preview")
@require_auth
def api_email_preview(email_id):
    con = get_db()
    row = con.execute("SELECT html_body FROM email_queue WHERE id = ?", (email_id,)).fetchone()
    con.close()
    if not row:
        abort(404)
    return row["html_body"], 200, {"Content-Type": "text/html"}


# ── API: logs ─────────────────────────────────────────────────────────────────

@app.route("/api/logs")
@require_auth
def api_logs():
    level = request.args.get("level", "all")
    page = max(1, int(request.args.get("page", 1)))
    limit = max(1, min(200, int(request.args.get("limit", 50))))
    offset = (page - 1) * limit

    valid_levels = ("error", "warning", "info")
    filter_level = level if level in valid_levels else None

    con = get_db()
    if filter_level:
        total = con.execute("SELECT COUNT(*) FROM logs WHERE level = ?", (filter_level,)).fetchone()[0]
        rows = con.execute(
            "SELECT id, created_at, level, company, request_id, message FROM logs WHERE level = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (filter_level, limit, offset),
        ).fetchall()
    else:
        total = con.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        rows = con.execute(
            "SELECT id, created_at, level, company, request_id, message FROM logs ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    con.close()
    logs = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "level": r["level"],
            "company": r["company"],
            "request_id": r["request_id"],
            "message": r["message"],
        }
        for r in rows
    ]
    return jsonify({"logs": logs, "total": total, "page": page, "limit": limit})


@app.route("/api/logs/<int:log_id>", methods=["DELETE"])
@require_auth
def api_delete_log(log_id):
    con = get_db()
    result = con.execute("DELETE FROM logs WHERE id = ?", (log_id,))
    con.commit()
    con.close()
    if result.rowcount == 0:
        return jsonify({"error": "not found"}), 404
    return "", 204


@app.route("/api/logs", methods=["DELETE"])
@require_auth
def api_clear_logs():
    con = get_db()
    con.execute("DELETE FROM logs")
    con.commit()
    con.close()
    return "", 204


@app.route("/api/email-queue/<int:email_id>", methods=["DELETE"])
@require_auth
def api_delete_email(email_id):
    con = get_db()
    row = con.execute("SELECT request_id FROM email_queue WHERE id = ?", (email_id,)).fetchone()
    if not row:
        con.close()
        return jsonify({"error": "not found"}), 404
    also_delete_job = request.args.get("delete_job") == "1"
    con.execute("DELETE FROM email_queue WHERE id = ?", (email_id,))
    if also_delete_job and row["request_id"]:
        con.execute("DELETE FROM jobs WHERE request_id = ?", (row["request_id"],))
    con.commit()
    con.close()
    return "", 204


# ── API: stats ────────────────────────────────────────────────────────────────

@app.route("/api/stats")
@require_auth
def api_stats():
    con = get_db()
    jobs_total = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    emails_pending = con.execute("SELECT COUNT(*) FROM email_queue WHERE sent_at IS NULL").fetchone()[0]
    emails_sent = con.execute("SELECT COUNT(*) FROM email_queue WHERE sent_at IS NOT NULL").fetchone()[0]
    errors_24h = con.execute(
        "SELECT COUNT(*) FROM logs WHERE level = 'error' AND created_at >= datetime('now', '-24 hours')"
    ).fetchone()[0]
    con.close()
    return jsonify({
        "jobs_total": jobs_total,
        "emails_pending": emails_pending,
        "emails_sent": emails_sent,
        "errors_24h": errors_24h,
    })


# ── SPA catch-all ─────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    dist = os.path.join(app.root_path, "frontend", "dist")
    target = os.path.join(dist, path)
    if path and os.path.exists(target):
        return send_from_directory(dist, path)
    index = os.path.join(dist, "index.html")
    if os.path.exists(index):
        return send_from_directory(dist, "index.html")
    return jsonify({"error": "frontend not built — run `npm run build` in frontend/"}), 404


# ── Boot ──────────────────────────────────────────────────────────────────────

ensure_tables()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
