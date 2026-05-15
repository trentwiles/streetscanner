#!/usr/bin/env python3
"""
scan.py — scraper cron
Reads verified, active queue entries, runs the appropriate scrapers,
and writes discovered trips to the DB.
Run on a schedule (e.g. every few hours via cron or systemd timer).
"""
import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

import db
import coachrun
import greyhound
import ourbus
import peterpan

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scan.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCAN_WINDOW_DAYS = 30

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

TIME_RANGES = {
    "Morning":   (5, 12),
    "Afternoon": (12, 17),
    "Night":     (17, 24),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dates_for_days(day_names: list[str]) -> list[date]:
    target_weekdays = {DAY_NAMES.index(d) for d in day_names if d in DAY_NAMES}
    today = date.today()
    return [
        today + timedelta(days=i)
        for i in range(SCAN_WINDOW_DAYS)
        if (today + timedelta(days=i)).weekday() in target_weekdays
    ]


def parse_hour(time_str: str) -> int | None:
    for fmt in (
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
        "%I:%M %p", "%I:%M%p", "%H:%M:%S", "%H:%M",
    ):
        try:
            return datetime.strptime(time_str.strip(), fmt).hour
        except ValueError:
            pass
    return None


def passes_time_filter(departs_at: str, filter_times: list[str]) -> bool:
    if not filter_times:
        return True
    hour = parse_hour(departs_at or "")
    if hour is None:
        return True
    return any(
        TIME_RANGES.get(t, (0, 24))[0] <= hour < TIME_RANGES.get(t, (0, 24))[1]
        for t in filter_times
    )


def combine(d: date, time_str: str) -> str:
    """Combine a date with a time-only string (e.g. '7:00 AM') into an ISO datetime."""
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(time_str.strip(), fmt).time()
            return datetime.combine(d, t).isoformat()
        except ValueError:
            pass
    return time_str


def save_trips(trips: list[dict]):
    now = datetime.now(timezone.utc).isoformat()
    with db.get_conn() as conn:
        inserted = 0
        for t in trips:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO trips
                    (trip_id, request_id, carrier, origin, destination,
                     departs_at, arrives_at, price_cents, booking_url, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    t["request_id"],
                    t["carrier"],
                    t["origin"],
                    t["destination"],
                    t["departs_at"],
                    t.get("arrives_at"),
                    t.get("price_cents"),
                    t.get("booking_url"),
                    now,
                ),
            )
            inserted += cur.rowcount
    return inserted

# ---------------------------------------------------------------------------
# Per-carrier adapters
# ---------------------------------------------------------------------------

def scan_coachrun(request_id, origin_id, dest_id, dates, times_filter):
    trips = []
    for d in dates:
        result = coachrun.search(origin_id, dest_id, d.strftime("%Y-%m-%d"))
        if isinstance(result, dict) and result.get("error"):
            log.warning("coachrun error on %s: %s", d, result["msg"])
            continue
        for t in result:
            departs_at = combine(d, t["departure"]) if t.get("departure") else None
            if not passes_time_filter(departs_at or "", times_filter):
                continue
            trips.append({
                "request_id": request_id,
                "carrier": "coachrun",
                "origin": origin_id,
                "destination": dest_id,
                "departs_at": departs_at,
                "arrives_at": combine(d, t["arrival"]) if t.get("arrival") else None,
                "price_cents": int(t["price"] * 100) if t.get("price") is not None else None,
                "booking_url": None,
            })
    return trips


def scan_greyhound(request_id, origin_id, dest_id, dates, times_filter):
    trips = []
    for d in dates:
        result = greyhound.searchTrip(origin_id, dest_id, d.strftime("%d.%m.%Y"))
        if isinstance(result, dict) and result.get("error"):
            log.warning("greyhound error on %s: %s", d, result["msg"])
            continue
        frontend_url = result.get("frontend_url")
        for t in result.get("options", []):
            departs_at = t.get("departure")
            if not passes_time_filter(departs_at or "", times_filter):
                continue
            price_usd = t.get("price_usd")
            trips.append({
                "request_id": request_id,
                "carrier": "greyhound",
                "origin": origin_id,
                "destination": dest_id,
                "departs_at": departs_at,
                "arrives_at": t.get("arrival"),
                "price_cents": int(price_usd * 100) if price_usd is not None else None,
                "booking_url": frontend_url,
            })
    return trips


def scan_ourbus(request_id, origin_id, dest_id, dates, times_filter):
    trips = []
    for d in dates:
        result = ourbus.search(origin_id, dest_id, d.strftime("%m/%d/%Y"))
        if isinstance(result, dict) and result.get("error"):
            log.warning("ourbus error on %s: %s", d, result["msg"])
            continue
        for t in result:
            departs_at = t.get("depart_time")
            if departs_at and "T" not in str(departs_at) and not str(departs_at)[:4].isdigit():
                departs_at = combine(d, departs_at)
            if not passes_time_filter(departs_at or "", times_filter):
                continue
            price = t.get("price")
            trips.append({
                "request_id": request_id,
                "carrier": "ourbus",
                "origin": origin_id,
                "destination": dest_id,
                "departs_at": departs_at,
                "arrives_at": t.get("arrive_time"),
                "price_cents": int(price * 100) if price is not None else None,
                "booking_url": None,
            })
    return trips


def scan_peterpan(request_id, origin_id, dest_id, dates, times_filter):
    trips = []
    for d in dates:
        raw = peterpan.search(origin_id, dest_id, d.strftime("%Y-%m-%d"))
        if isinstance(raw, dict) and raw.get("error"):
            log.warning("peterpan error on %s: %s", d, raw["msg"])
            continue
        result = json.loads(raw) if isinstance(raw, str) else raw
        for t in result:
            departs_at = t.get("depart_time")
            if departs_at and "T" not in str(departs_at) and not str(departs_at)[:4].isdigit():
                departs_at = combine(d, departs_at)
            if not passes_time_filter(departs_at or "", times_filter):
                continue
            price = t.get("price")
            trips.append({
                "request_id": request_id,
                "carrier": "peterpan",
                "origin": origin_id,
                "destination": dest_id,
                "departs_at": departs_at,
                "arrives_at": t.get("arrive_time"),
                "price_cents": int(price * 100) if price is not None else None,
                "booking_url": None,
            })
    return trips


SCANNERS = {
    "coachrun": scan_coachrun,
    "greyhound": scan_greyhound,
    "ourbus":    scan_ourbus,
    "peterpan":  scan_peterpan,
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    db.init_db()
    requests = db.list_verified_queue()
    log.info("Found %d verified request(s) to process", len(requests))

    for req in requests:
        request_id = req["request_id"]
        origin = req["origin_city"]
        destination = req["dest_city"]
        leave_days = json.loads(req["leave_days"] or "[]")
        times_filter = json.loads(req["times"] or "[]")

        log.info("[%s] %s → %s  days=%s times=%s",
                 request_id[:8], origin, destination, leave_days, times_filter)

        if not leave_days:
            log.warning("[%s] no leave_days set, skipping", request_id[:8])
            continue

        dates = dates_for_days(leave_days)
        origin_trans = db.get_all_translations(origin)
        dest_trans = db.get_all_translations(destination)
        shared = set(origin_trans) & set(dest_trans)

        if not shared:
            log.warning("[%s] no shared carriers for route, skipping", request_id[:8])
            continue

        all_trips = []
        for carrier in shared:
            scanner = SCANNERS.get(carrier)
            if not scanner:
                continue
            log.info("  scanning %s (%d date(s))…", carrier, len(dates))
            try:
                found = scanner(
                    request_id,
                    origin_trans[carrier],
                    dest_trans[carrier],
                    dates,
                    times_filter,
                )
                log.info("  → %d trip(s) found", len(found))
                all_trips.extend(found)
            except Exception:
                log.exception("  ERROR scanning %s for request %s", carrier, request_id[:8])

        if all_trips:
            all_trips.sort(key=lambda t: (t.get("price_cents") is None, t.get("price_cents")))
            cheapest = all_trips[:5]
            inserted = save_trips(cheapest)
            log.info("[%s] saved %d new trip(s) (%d dupes skipped, %d dropped beyond top-5)",
                     request_id[:8], inserted, len(cheapest) - inserted, len(all_trips) - len(cheapest))

    log.info("Scan complete")


if __name__ == "__main__":
    run()
