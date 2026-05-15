#!/usr/bin/env python3
"""
notify.py — email digest cron
Bundles unnotified trips per user and sends a single digest email.
Run on a schedule after scan.py (e.g. 30 minutes later via cron).
"""
import logging
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

from dotenv import load_dotenv

import db

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/notify.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def _send(to_email: str, subject: str, body: str):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    from_addr = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_host:
        log.info("[dry-run] to=%s subject=%r\n%s", to_email, subject, body)
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


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

CARRIER_LABELS = {
    "coachrun": "CoachRun",
    "greyhound": "Greyhound",
    "ourbus":    "OurBus",
    "peterpan":  "Peter Pan",
}


def fmt_price(price_cents: int | None) -> str:
    if price_cents is None:
        return "price unavailable"
    return f"${price_cents / 100:.2f}"


def fmt_time(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    # Try to extract a readable time from ISO or plain string
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            from datetime import datetime
            dt = datetime.strptime(iso_str, fmt)
            return dt.strftime("%-I:%M %p on %b %-d")
        except ValueError:
            pass
    return iso_str


def build_body(trips: list[dict], manage_link: str) -> str:
    # Group trips by route (origin_city → dest_city)
    by_route: dict[str, list[dict]] = {}
    for t in trips:
        key = f"{t['origin_city']} → {t['dest_city']}"
        by_route.setdefault(key, []).append(t)

    lines = ["Here are the latest bus trips we found for you.\n"]

    for route, route_trips in by_route.items():
        lines.append(f"  {route}")
        lines.append("  " + "-" * len(route))

        for t in route_trips:
            carrier = CARRIER_LABELS.get(t["carrier"], t["carrier"])
            departs = fmt_time(t["departs_at"])
            arrives = fmt_time(t["arrives_at"])
            price = fmt_price(t["price_cents"])

            lines.append(f"  {carrier}  |  Departs {departs}  |  Arrives {arrives}  |  {price}")
            if t.get("booking_url"):
                lines.append(f"  Book: {t['booking_url']}")

        lines.append("")

    lines += [
        "─" * 60,
        "View all trips and manage your subscriptions:",
        manage_link,
        "",
        "You're receiving this because you set up a bus alert at Street Scanner.",
        "To unsubscribe, visit the link above.",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    db.init_db()
    by_email = db.get_unnotified_trips_by_email()

    if not by_email:
        log.info("No unnotified trips — nothing to send")
        return

    log.info("Sending digests to %d recipient(s)", len(by_email))
    base_url = os.environ.get("BASE_URL", "").rstrip("/")

    for email, trips in by_email.items():
        log.info("  %s — %d trip(s)", email, len(trips))

        token = db.create_magic_link(email)
        if base_url:
            manage_link = f"{base_url}/trips?{urlencode({'auth': token})}"
        else:
            manage_link = f"http://localhost:5000/trips?{urlencode({'auth': token})}"

        body = build_body(trips, manage_link)
        route_summary = ", ".join(
            {f"{t['origin_city']} → {t['dest_city']}" for t in trips}
        )
        subject = f"Street Scanner: trips found for {route_summary}"

        try:
            _send(email, subject, body)
            db.mark_trips_notified([t["trip_id"] for t in trips])
            log.info("  sent and marked %d trip(s) as notified", len(trips))
        except Exception:
            log.exception("  failed to send digest to %s", email)


if __name__ == "__main__":
    run()
