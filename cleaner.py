"""
cleaner.py — normalize raw scraper output and render an HTML email digest.

Input:  date_results: dict[date_str, dict[company, list|dict|None]]
        (the structure returned by jobFufil.search_all_companies, keyed by date)
Output: sorted list of normalized trips + HTML string ready for the email queue
"""

from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)

COMPANY_DISPLAY = {
    "greyhound": "Greyhound / Flixbus",
    "peterpan": "Peter Pan",
    "ourbus": "OurBus",
    "coachrun": "Coachrun",
}


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _parse_time(value: Optional[str]) -> Optional[str]:
    """Extract HH:MM from any of the time/datetime formats the scrapers return."""
    if not value:
        return None
    value = str(value).strip()
    # ISO 8601: "2026-05-01T14:30:00" or "2026-05-01T14:30:00+00:00"
    m = re.search(r"T(\d{2}:\d{2})", value)
    if m:
        return m.group(1)
    # Full datetime: "2026-05-01 14:30" or "2026-05-01 14:30:00"
    m = re.search(r"\d{4}-\d{2}-\d{2}\s+(\d{2}:\d{2})", value)
    if m:
        return m.group(1)
    # Plain time: "14:30:00" or "14:30"
    m = re.match(r"(\d{2}:\d{2})", value)
    if m:
        return m.group(1)
    return value


def _parse_duration(trip: dict, company: str) -> Optional[str]:
    """Produce a human-readable duration string from any scraper's trip dict."""
    if company == "greyhound":
        h = trip.get("duration_hours")
        m = trip.get("duration_minutes")
        if h is not None and m is not None:
            return f"{h}h {m}m"
    elif company == "peterpan":
        raw = trip.get("duration")
        if raw is not None:
            try:
                total = int(raw)
                return f"{total // 60}h {total % 60}m"
            except (ValueError, TypeError):
                return str(raw)
    elif company == "coachrun":
        return trip.get("duration")  # already "Xh Ym"
    return None  # ourbus has no duration


def _price(trip: dict, company: str) -> Optional[float]:
    """Return price as a float regardless of field name."""
    if company == "greyhound":
        return trip.get("price_usd")
    return trip.get("price")


def normalize_trip(company: str, date: str, trip: dict) -> dict:
    """Return a canonical trip dict from any scraper's raw output."""
    return {
        "company": company,
        "company_display": COMPANY_DISPLAY.get(company, company),
        "date": date,
        "price": _price(trip, company),
        "depart_time": _parse_time(trip.get("depart_time") or trip.get("departure")),
        "arrive_time": _parse_time(trip.get("arrive_time") or trip.get("arrival")),
        "duration": _parse_duration(trip, company),
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def collect_trips(date_results: dict[str, dict]) -> list[dict]:
    """
    Flatten date_results into a sorted list of normalized trips.

    date_results shape:
        { "YYYY-MM-DD": { company: [trip, ...] | {"error": ...} | None } }
    """
    flat: list[dict] = []
    for date, company_map in date_results.items():
        for company, trips in company_map.items():
            if not isinstance(trips, list):
                continue
            for trip in trips:
                norm = normalize_trip(company, date, trip)
                if norm["price"] is not None:
                    flat.append(norm)

    flat.sort(key=lambda t: (t["date"], t["price"]))
    return flat


# ---------------------------------------------------------------------------
# HTML email renderer
# ---------------------------------------------------------------------------

def _date_heading(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d")
    except ValueError:
        return date_str


def render_email_html(
    origin: str,
    dest: str,
    trips: list[dict],
    *,
    max_overall: int = 5,
) -> str:
    overall = sorted(trips, key=lambda t: t["price"])[:max_overall]

    dates_seen: list[str] = []
    by_date: dict[str, list[dict]] = {}
    for t in trips:
        d = t["date"]
        if d not in by_date:
            by_date[d] = []
            dates_seen.append(d)
        by_date[d].append(t)

    def _fmt(t: dict) -> dict:
        return {**t, "formatted_price": f"${t['price']:.2f}", "date_heading": _date_heading(t["date"])}

    context = {
        "origin": origin,
        "dest": dest,
        "trip_count": len(trips),
        "overall": [_fmt(t) for t in overall],
        "date_sections": [
            {"heading": _date_heading(d), "trips": [_fmt(t) for t in by_date[d]]}
            for d in dates_seen
        ],
    }

    return _jinja_env.get_template("email_digest.html").render(**context)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def render_email_subject(origin: str, dest: str, dates: list[str]) -> str:
    """Return a plain-text email subject line."""
    if not dates:
        return f"Bus prices: {origin} → {dest}"
    def fmt(d: str) -> str:
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%b %-d")
        except ValueError:
            return d
    sorted_dates = sorted(dates)
    if len(sorted_dates) == 1:
        date_part = fmt(sorted_dates[0])
    else:
        date_part = f"{fmt(sorted_dates[0])} – {fmt(sorted_dates[-1])}"
    return f"Bus prices: {origin} → {dest} | {date_part}"


def prepare_email(
    origin: str,
    dest: str,
    date_results: dict[str, dict],
) -> tuple[list[dict], str, str]:
    """
    Given raw date_results from jobFufil.search_all_companies (keyed by date),
    return (sorted_trips, subject, html_string).
    """
    trips = collect_trips(date_results)
    subject = render_email_subject(origin, dest, list(date_results.keys()))
    html = render_email_html(origin, dest, trips)
    return trips, subject, html
