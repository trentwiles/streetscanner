"""
Seed the local streetscanner.db with sample cities, translations, and jobs.
Run from the project root: python tests/seed_jobs.py
"""

import sqlite3
import uuid
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "streetscanner.db")


def create_tables(con):
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
            originCity        TEXT NOT NULL REFERENCES cities(city),
            destCity          TEXT NOT NULL REFERENCES cities(city),
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
    """)


CITIES = [
    ("New York",    "new-york"),
    ("Boston",      "boston"),
    ("Washington",  "washington"),
    ("Philadelphia","philadelphia"),
]

# identifier values match each scraper's expected format
TRANSLATIONS = [
    # PeterPan uses stop UUIDs (sourced from peterpan.py test call + searchCity)
    ("peterpan", "new-york",     "31489613-da82-4b96-97c3-c75415f63ba0"),
    ("peterpan", "boston",       "ff873135-3313-45f9-99fd-8f1c1be9a3a2"),

    # Greyhound/Flixbus uses city UUIDs (sourced from greyhound.py COMMON_CITIES)
    ("greyhound", "new-york",    "c0a47c54-53ea-46dc-984b-b764fc0b2fa9"),
    ("greyhound", "boston",      "eeff627f-2fda-4e75-8468-783d47955b3a"),

    # OurBus uses plain English city names matching its STOPS list
    ("ourbus", "new-york",       "New York, NY"),
    ("ourbus", "boston",         "Boston, MA"),
    ("ourbus", "washington",     "Washington, DC"),
    ("ourbus", "philadelphia",   "Philadelphia International Airport, PA"),

    # Coachrun uses plain English city names matching its CITIES list
    ("coachrun", "new-york",     "New York, NY"),
    ("coachrun", "boston",       "Boston, MA"),
    ("coachrun", "washington",   "Washington, DC"),
    ("coachrun", "philadelphia", "Philadelphia, PA"),
]

JOBS = [
    {
        "email":             "alice@example.com",
        "submit_ip":         "127.0.0.1",
        "submit_user_agent": "Mozilla/5.0 (test)",
        "originCity":        "New York",
        "destCity":          "Boston",
        "days":              "Fri,Sat",
    },
    {
        "email":             "bob@example.com",
        "submit_ip":         "127.0.0.1",
        "submit_user_agent": "Mozilla/5.0 (test)",
        "originCity":        "Boston",
        "destCity":          "New York",
        "days":              "Sun,Mon",
    },
    {
        "email":             "carol@example.com",
        "submit_ip":         "10.0.0.1",
        "submit_user_agent": "Mozilla/5.0 (test)",
        "originCity":        "New York",
        "destCity":          "Washington",
        "days":              "Mon,Tue,Wed,Thu,Fri",
    },
]


def seed(con):
    now = datetime.now(timezone.utc).isoformat()

    for city, city_id in CITIES:
        con.execute(
            "INSERT OR IGNORE INTO cities (id, city) VALUES (?, ?)",
            (city_id, city),
        )

    for company, city_id, identifier in TRANSLATIONS:
        con.execute(
            "INSERT OR REPLACE INTO translations (bus_company, city_id, identifier) VALUES (?, ?, ?)",
            (company, city_id, identifier),
        )

    for job in JOBS:
        con.execute(
            """INSERT INTO jobs
               (request_id, email, submit_ip, submit_time, submit_user_agent, originCity, destCity, days)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                job["email"],
                job["submit_ip"],
                now,
                job["submit_user_agent"],
                job["originCity"],
                job["destCity"],
                job["days"],
            ),
        )

    con.commit()


if __name__ == "__main__":
    con = sqlite3.connect(DB_PATH)
    create_tables(con)
    seed(con)
    con.close()

    print(f"Seeded {len(CITIES)} cities, {len(TRANSLATIONS)} translations, {len(JOBS)} jobs -> {os.path.abspath(DB_PATH)}")
