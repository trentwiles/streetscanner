import os
import smtplib
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlencode

from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))


@app.template_filter("fromjson")
def fromjson_filter(s):
    import json
    try:
        return json.loads(s or "[]")
    except (ValueError, TypeError):
        return []


@app.template_filter("fmttime")
def fmt_time_filter(iso_str):
    if not iso_str:
        return "—"
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(iso_str, fmt).strftime("%-I:%M %p, %b %-d")
        except ValueError:
            pass
    return iso_str


@app.template_filter("fmtprice")
def fmt_price_filter(cents):
    if cents is None:
        return "N/A"
    return f"${cents / 100:.2f}"


def _smtp_send(to_email: str, subject: str, body: str):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    from_addr = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_host:
        print(f"[email] to={to_email} subject={subject!r}\n{body}")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        if smtp_user:
            s.starttls()
            s.login(smtp_user, smtp_pass)
        s.send_message(msg)


def _send_magic_link_email(to_email: str, link: str):
    _smtp_send(
        to_email,
        "Your Street Scanner login link",
        f"Click the link below to sign in to Street Scanner.\n\n"
        f"{link}\n\n"
        f"This link expires in {db.MAGIC_LINK_TTL_MINUTES} minutes and can only be used once.",
    )


def _send_verification_email(to_email: str, link: str):
    _smtp_send(
        to_email,
        "Confirm your Street Scanner alert",
        f"Thanks for setting up a bus alert with Street Scanner!\n\n"
        f"Click the link below to confirm your alert. Once confirmed, we'll start "
        f"scanning for trips and email you when we find something.\n\n"
        f"{link}\n\n"
        f"This link expires in {db.MAGIC_LINK_TTL_MINUTES} minutes and can only be used once.\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"(If this email landed in spam, please mark it as 'not spam' so future "
        f"trip alerts reach your inbox.)",
    )


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    cities = db.list_cities()
    return render_template("index.html", cities=cities)


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()

    email = (data.get("email") or "").strip()
    origin = (data.get("origin") or "").strip()
    dest = (data.get("dest") or "").strip()
    leave_days = data.get("leave_days") or []
    return_days = data.get("return_days") or []
    times = data.get("times") or []

    if not email or not origin or not dest:
        return jsonify({"ok": False, "error": "Email, origin, and destination are required."}), 400
    if origin == dest:
        return jsonify({"ok": False, "error": "Origin and destination must be different."}), 400

    origin_carriers = set(db.get_all_translations(origin).keys())
    dest_carriers = set(db.get_all_translations(dest).keys())
    if not origin_carriers & dest_carriers:
        return jsonify({"ok": False, "error": "No bus line serves both cities. Please choose a different route."}), 400

    if not leave_days:
        return jsonify({"ok": False, "error": "Select at least one leave day."}), 400

    try:
        request_id = db.enqueue_request(
            email=email,
            submit_ip=request.remote_addr,
            submit_ua=request.headers.get("User-Agent", ""),
            origin_city_name=origin,
            dest_city_name=dest,
            leave_days=leave_days,
            return_days=return_days,
            times=times,
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    token = db.create_magic_link(email, request_id)
    base_url = os.environ.get("BASE_URL", "").rstrip("/")
    verify_link = (
        f"{base_url}/auth/verify?token={token}"
        if base_url
        else url_for("verify_magic_link", token=token, _external=True)
    )
    _send_verification_email(email, verify_link)

    return jsonify({"ok": True, "request_id": request_id})


@app.route("/login")
def login():
    if "email" in session:
        return redirect(url_for("me"))
    return render_template("login.html")


@app.route("/auth/magic-link", methods=["POST"])
def send_magic_link():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"ok": False, "error": "Email is required."}), 400

    token = db.create_magic_link(email)
    base_url = os.environ.get("BASE_URL", "").rstrip("/")
    if base_url:
        # TODO: replace placeholder with a unique string derived from the recipient
        link = f"{base_url}/trips?{urlencode({'auth': token, 'email': 'PLACEHOLDER'})}"
    else:
        link = url_for("verify_magic_link", token=token, _external=True)
    _send_magic_link_email(email, link)
    return jsonify({"ok": True})


@app.route("/auth/verify")
def verify_magic_link():
    token = request.args.get("token", "")
    email = db.consume_magic_link(token)
    if not email:
        return render_template("login.html", error="This link is invalid or has expired."), 400
    session["email"] = email
    return render_template("verified.html")


@app.route("/trips")
def trips():
    token = request.args.get("auth", "")
    if token:
        verified_email = db.consume_magic_link(token)
        if not verified_email:
            return render_template("login.html", error="This link is invalid or has expired."), 400
        session["email"] = verified_email
    if "email" not in session:
        return redirect(url_for("login"))
    subscriptions = db.get_subscriptions_with_trips(session["email"])
    return render_template("trips.html", email=session["email"], subscriptions=subscriptions)


@app.route("/unsubscribe/<request_id>", methods=["POST"])
@login_required
def unsubscribe(request_id):
    success = db.deactivate_subscription(request_id, session["email"])
    if not success:
        return jsonify({"ok": False, "error": "Subscription not found."}), 404
    return jsonify({"ok": True})


@app.route("/unsubscribe-all", methods=["POST"])
@login_required
def unsubscribe_all():
    count = db.deactivate_all_subscriptions(session["email"])
    return jsonify({"ok": True, "deactivated": count})


@app.route("/me")
@login_required
def me():
    return render_template("me.html", email=session["email"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=50003, host='0.0.0.0')
