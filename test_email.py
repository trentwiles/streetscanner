#!/usr/bin/env python3
"""Send a test email using the same SMTP config as the app."""

import os
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage

from dotenv import load_dotenv
load_dotenv()

smtp_host = os.environ.get("SMTP_HOST")
smtp_port = int(os.environ.get("SMTP_PORT", 587))
smtp_user = os.environ.get("SMTP_USER", "")
smtp_pass = os.environ.get("SMTP_PASS", "")
from_addr = os.environ.get("SMTP_FROM", smtp_user)

to_addr = sys.argv[1] if len(sys.argv) > 1 else smtp_user

def log(label, value=""):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if value:
        print(f"[{ts}] {label}: {value}")
    else:
        print(f"[{ts}] {label}")

log("SMTP_HOST", smtp_host or "(not set)")
log("SMTP_PORT", smtp_port)
log("SMTP_USER", smtp_user or "(not set)")
log("SMTP_FROM", from_addr or "(not set)")
log("TO",        to_addr)
print()

if not smtp_host:
    print("ERROR: SMTP_HOST is not set. Export it and re-run.")
    sys.exit(1)

if not to_addr:
    print("ERROR: No recipient. Pass an email as the first argument or set SMTP_USER.")
    sys.exit(1)

msg = EmailMessage()
msg["Subject"] = "Street Scanner — email test"
msg["From"]    = from_addr
msg["To"]      = to_addr
msg.set_content(
    f"This is a test email from Street Scanner.\n\n"
    f"Sent at {datetime.now(timezone.utc).isoformat()} UTC."
)

log("Connecting", f"{smtp_host}:{smtp_port}")
try:
    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.set_debuglevel(1)

        log("EHLO")
        s.ehlo()

        if smtp_user:
            log("STARTTLS")
            s.starttls()
            s.ehlo()

        if smtp_user:
            log("LOGIN", smtp_user)
            s.login(smtp_user, smtp_pass)

        log("SEND", f"{from_addr} → {to_addr}")
        s.send_message(msg)

    print()
    log("OK — email sent")
except smtplib.SMTPAuthenticationError as e:
    print()
    log("AUTH ERROR", str(e))
    sys.exit(1)
except smtplib.SMTPException as e:
    print()
    log("SMTP ERROR", str(e))
    sys.exit(1)
except OSError as e:
    print()
    log("CONNECTION ERROR", str(e))
    sys.exit(1)
