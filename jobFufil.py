import sqlite3
import json
import sys
import random
import time
from datetime import datetime, timedelta

import peterpan
import ourbus
import coachrun
import greyhound
import cleaner

DB_PATH = "streetscanner.db"

DAY_ABBREVS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SEARCH_WEEKS_AHEAD = 4

SLEEP_MIN = 10
SLEEP_MAX = 30


def dates_for_days(days_str: str) -> list[str]:
    """Return YYYY-MM-DD dates for the requested weekdays over the next SEARCH_WEEKS_AHEAD weeks."""
    requested = {d.strip() for d in days_str.split(",")}
    today = datetime.today().date()
    dates = []
    for offset in range(SEARCH_WEEKS_AHEAD * 7):
        candidate = today + timedelta(days=offset)
        if DAY_ABBREVS[candidate.weekday()] in requested:
            dates.append(candidate.strftime("%Y-%m-%d"))
    return dates


def log(level: str, message: str, *, company: str = None, request_id: str = None) -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO logs (created_at, level, company, request_id, message) VALUES (?, ?, ?, ?, ?)",
        (datetime.utcnow().isoformat(), level, company, request_id, message),
    )
    con.commit()
    con.close()


def get_jobs():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    jobs = con.execute("SELECT * FROM jobs").fetchall()
    con.close()
    return [dict(j) for j in jobs]


def search_all_companies(origin_city_id: str, dest_city_id: str, date: str) -> dict:
    """Search all bus companies for trips. date: YYYY-MM-DD"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    results = {}
    d = datetime.strptime(date, "%Y-%m-%d")

    for company in ("peterpan", "ourbus", "coachrun", "greyhound"):
        origin_row = con.execute(
            "SELECT identifier FROM translations WHERE bus_company = ? AND city_id = ?",
            (company, origin_city_id),
        ).fetchone()
        dest_row = con.execute(
            "SELECT identifier FROM translations WHERE bus_company = ? AND city_id = ?",
            (company, dest_city_id),
        ).fetchone()

        if not origin_row or not dest_row:
            results[company] = None
            continue

        origin_id = origin_row["identifier"]
        dest_id = dest_row["identifier"]

        try:
            if company == "peterpan":
                raw = peterpan.search(origin_id, dest_id, date)
                results[company] = json.loads(raw) if isinstance(raw, str) else raw
            elif company == "ourbus":
                results[company] = ourbus.search(origin_id, dest_id, d.strftime("%m/%d/%Y"))
            elif company == "coachrun":
                results[company] = coachrun.search(origin_id, dest_id, date)
            elif company == "greyhound":
                raw = greyhound.searchTrip(origin_id, dest_id, d.strftime("%d.%m.%Y"))
                # unwrap options list; leave error dicts intact for display
                results[company] = raw.get("options", []) if isinstance(raw, dict) and "options" in raw else raw
        except Exception as e:
            results[company] = {"error": str(e)}

    con.close()
    return results


def fulfill_jobs():
    jobs = get_jobs()
    if not jobs:
        print("No jobs found in queue.")
        return

    n = len(jobs)
    est_min = n * SLEEP_MIN
    est_max = n * SLEEP_MAX
    estimate_msg = f"{n} job(s) queued; estimated runtime {est_min}s–{est_max}s (sleep {SLEEP_MIN}s–{SLEEP_MAX}s between jobs)"
    print(estimate_msg)
    log("info", estimate_msg)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    for i, job in enumerate(jobs):
        origin_name = job["originCity"]
        dest_name = job["destCity"]
        days_str = job.get("days", "")

        print(f"\n{'='*60}")
        print(f"Job:   {job['request_id']}")
        print(f"Route: {origin_name} -> {dest_name}")
        print(f"Days:  {days_str}")
        print("=" * 60)

        if not days_str:
            print("  [!] no days specified, skipping")
            log("warning", "no days specified, skipping", request_id=job["request_id"])
            continue

        origin_row = con.execute("SELECT id FROM cities WHERE city = ?", (origin_name,)).fetchone()
        dest_row = con.execute("SELECT id FROM cities WHERE city = ?", (dest_name,)).fetchone()

        if not origin_row or not dest_row:
            print("  [!] city not found in cities table, skipping")
            log("error", f"city not found in cities table: '{origin_name}' or '{dest_name}'", request_id=job["request_id"])
            continue

        search_dates = dates_for_days(days_str)

        date_results = {}
        for date in search_dates:
            print(f"\n  -- {date} --")
            results = search_all_companies(origin_row["id"], dest_row["id"], date)
            date_results[date] = results

            for company, trips in results.items():
                print(f"\n  [{company.upper()}]")
                if trips is None:
                    print("    no route translations found")
                elif isinstance(trips, dict) and "error" in trips:
                    msg = trips.get("msg", trips["error"])
                    print(f"    error: {msg}")
                    log("error", msg, company=company, request_id=job["request_id"])
                elif not trips:
                    print("    no trips found")
                else:
                    for trip in trips:
                        print(f"    {trip}")

        sorted_trips, subject, html = cleaner.prepare_email(origin_name, dest_name, date_results)
        print(f"\n  [CLEANER] {len(sorted_trips)} trips normalized")

        now = datetime.utcnow().isoformat()
        con.execute(
            """INSERT INTO email_queue (request_id, email, subject, html_body, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (job["request_id"], job["email"], subject, html, now),
        )
        con.commit()
        print(f"  [QUEUE]   queued email → {job['email']} | {subject}")

        if i < n - 1:
            delay = random.randint(SLEEP_MIN, SLEEP_MAX)
            print(f"  [SLEEP]   waiting {delay}s before next job...")
            time.sleep(delay)

    con.close()


if __name__ == "__main__":
    fulfill_jobs()
