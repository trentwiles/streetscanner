import sqlite3
import uuid
import secrets
from datetime import datetime, timezone, timedelta

DB_PATH = "street_scanner.db"

MAGIC_LINK_TTL_MINUTES = 15


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cities (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS translations (
                id          TEXT PRIMARY KEY,
                city_id     TEXT NOT NULL REFERENCES cities(id),
                carrier     TEXT NOT NULL,
                identifier  TEXT NOT NULL,
                UNIQUE(city_id, carrier)
            );

            CREATE TABLE IF NOT EXISTS magic_links (
                token       TEXT PRIMARY KEY,
                email       TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                used        INTEGER NOT NULL DEFAULT 0,
                request_id  TEXT REFERENCES queue(request_id)
            );

            CREATE TABLE IF NOT EXISTS queue (
                request_id      TEXT PRIMARY KEY,
                email           TEXT NOT NULL,
                submit_ip       TEXT,
                submit_time     TEXT NOT NULL,
                submit_ua       TEXT,
                origin_city_id  TEXT NOT NULL REFERENCES cities(id),
                dest_city_id    TEXT NOT NULL REFERENCES cities(id),
                leave_days      TEXT,
                return_days     TEXT,
                times           TEXT,
                verified        INTEGER NOT NULL DEFAULT 0,
                active          INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS trips (
                trip_id       TEXT PRIMARY KEY,
                request_id    TEXT NOT NULL REFERENCES queue(request_id),
                carrier       TEXT NOT NULL,
                origin        TEXT NOT NULL,
                destination   TEXT NOT NULL,
                departs_at    TEXT NOT NULL,
                arrives_at    TEXT,
                price_cents   INTEGER,
                booking_url   TEXT,
                discovered_at TEXT NOT NULL
            );
        """)
        # Migrate pre-existing tables that lack new columns
        queue_cols = {r[1] for r in conn.execute("PRAGMA table_info(queue)").fetchall()}
        for col, defn in [
            ("leave_days", "TEXT"),
            ("return_days", "TEXT"),
            ("times", "TEXT"),
            ("verified", "INTEGER NOT NULL DEFAULT 0"),
            ("active", "INTEGER NOT NULL DEFAULT 1"),
        ]:
            if col not in queue_cols:
                conn.execute(f"ALTER TABLE queue ADD COLUMN {col} {defn}")

        ml_cols = {r[1] for r in conn.execute("PRAGMA table_info(magic_links)").fetchall()}
        if "request_id" not in ml_cols:
            conn.execute("ALTER TABLE magic_links ADD COLUMN request_id TEXT REFERENCES queue(request_id)")

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS trips_dedup
            ON trips (request_id, carrier, departs_at)
        """)

        trips_cols = {r[1] for r in conn.execute("PRAGMA table_info(trips)").fetchall()}
        if "notified_at" not in trips_cols:
            conn.execute("ALTER TABLE trips ADD COLUMN notified_at TEXT")


# --- cities ---

def add_city(name: str) -> str:
    """Insert a city by canonical name. Returns its UUID (existing or new)."""
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM cities WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        city_id = str(uuid.uuid4())
        conn.execute("INSERT INTO cities (id, name) VALUES (?, ?)", (city_id, name))
        return city_id


def get_city(name: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM cities WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def list_cities() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM cities ORDER BY name").fetchall()
        results = []
        for row in rows:
            carriers = sorted(
                r["carrier"]
                for r in conn.execute(
                    "SELECT carrier FROM translations WHERE city_id = ?", (row["id"],)
                ).fetchall()
            )
            results.append({"id": row["id"], "name": row["name"], "carriers": carriers})
        return results


CARRIERS = ("coachrun", "greyhound", "ourbus", "peterpan")


def search_cities(q: str) -> list[dict]:
    """
    Return cities whose name contains q (case-insensitive), each with a
    per-carrier bool indicating whether a translation exists.

    Example result:
      [{"city": "New York, NY", "coachrun": True, "greyhound": True, "ourbus": True, "peterpan": True}]
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cities WHERE LOWER(name) LIKE ? ORDER BY name",
            (f"%{q.lower()}%",),
        ).fetchall()

        results = []
        for row in rows:
            carriers = {
                carrier: conn.execute(
                    "SELECT 1 FROM translations WHERE city_id = ? AND carrier = ?",
                    (row["id"], carrier),
                ).fetchone() is not None
                for carrier in CARRIERS
            }
            results.append({"city": row["name"], **carriers})
        return results


# --- translations ---

# carrier values: "greyhound", "peterpan", "ourbus", "coachrun"
def add_translation(city_id: str, carrier: str, identifier: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO translations (id, city_id, carrier, identifier)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(city_id, carrier) DO UPDATE SET identifier = excluded.identifier
            """,
            (str(uuid.uuid4()), city_id, carrier, identifier),
        )


def get_translation(city_name: str, carrier: str) -> str | None:
    """Return the carrier-specific identifier for a city, or None if not mapped."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT t.identifier
            FROM translations t
            JOIN cities c ON c.id = t.city_id
            WHERE c.name = ? AND t.carrier = ?
            """,
            (city_name, carrier),
        ).fetchone()
        return row["identifier"] if row else None


def get_all_translations(city_name: str) -> dict:
    """Return all carrier identifiers for a city as {carrier: identifier}."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.carrier, t.identifier
            FROM translations t
            JOIN cities c ON c.id = t.city_id
            WHERE c.name = ?
            """,
            (city_name,),
        ).fetchall()
        return {r["carrier"]: r["identifier"] for r in rows}


# --- queue ---

def enqueue_request(email: str, submit_ip: str, submit_ua: str,
                    origin_city_name: str, dest_city_name: str,
                    leave_days: list[str] = None, return_days: list[str] = None,
                    times: list[str] = None) -> str:
    import json
    from datetime import datetime, timezone

    origin = get_city(origin_city_name)
    dest = get_city(dest_city_name)
    if not origin:
        raise ValueError(f"Unknown city: {origin_city_name}")
    if not dest:
        raise ValueError(f"Unknown city: {dest_city_name}")

    request_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO queue
                (request_id, email, submit_ip, submit_time, submit_ua,
                 origin_city_id, dest_city_id, leave_days, return_days, times)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, email, submit_ip,
             datetime.now(timezone.utc).isoformat(),
             submit_ua, origin["id"], dest["id"],
             json.dumps(leave_days or []),
             json.dumps(return_days or []),
             json.dumps(times or [])),
        )
    return request_id


def list_queue() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT q.*, oc.name AS origin_city, dc.name AS dest_city
            FROM queue q
            JOIN cities oc ON oc.id = q.origin_city_id
            JOIN cities dc ON dc.id = q.dest_city_id
            ORDER BY q.submit_time
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_unnotified_trips_by_email() -> dict[str, list[dict]]:
    """Return unnotified trips grouped by email: {email: [trip_rows]}."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.*, q.email,
                   oc.name AS origin_city, dc.name AS dest_city
            FROM trips t
            JOIN queue q ON q.request_id = t.request_id
            JOIN cities oc ON oc.id = q.origin_city_id
            JOIN cities dc ON dc.id = q.dest_city_id
            WHERE t.notified_at IS NULL
            ORDER BY q.email, t.departs_at
            """
        ).fetchall()

    by_email: dict[str, list[dict]] = {}
    for row in rows:
        email = row["email"]
        by_email.setdefault(email, []).append(dict(row))
    return by_email


def get_subscriptions_with_trips(email: str) -> list[dict]:
    """Return all active, verified subscriptions for an email, each with their trips."""
    with get_conn() as conn:
        subs = conn.execute(
            """
            SELECT q.*, oc.name AS origin_city, dc.name AS dest_city
            FROM queue q
            JOIN cities oc ON oc.id = q.origin_city_id
            JOIN cities dc ON dc.id = q.dest_city_id
            WHERE q.email = ? AND q.verified = 1 AND q.active = 1
            ORDER BY q.submit_time
            """,
            (email,),
        ).fetchall()

        result = []
        for sub in subs:
            trips = conn.execute(
                "SELECT * FROM trips WHERE request_id = ? ORDER BY departs_at",
                (sub["request_id"],),
            ).fetchall()
            result.append({**dict(sub), "trips": [dict(t) for t in trips]})
        return result


def deactivate_subscription(request_id: str, email: str) -> bool:
    """Set active=0. Returns True if a row was updated (email must match)."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE queue SET active = 0 WHERE request_id = ? AND email = ?",
            (request_id, email),
        )
        return cur.rowcount > 0


def deactivate_all_subscriptions(email: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE queue SET active = 0 WHERE email = ? AND active = 1",
            (email,),
        )
        return cur.rowcount


def mark_trips_notified(trip_ids: list[str]):
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.executemany(
            "UPDATE trips SET notified_at = ? WHERE trip_id = ?",
            [(now, tid) for tid in trip_ids],
        )


def list_verified_queue() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT q.*, oc.name AS origin_city, dc.name AS dest_city
            FROM queue q
            JOIN cities oc ON oc.id = q.origin_city_id
            JOIN cities dc ON dc.id = q.dest_city_id
            WHERE q.verified = 1 AND q.active = 1
            ORDER BY q.submit_time
            """
        ).fetchall()
        return [dict(r) for r in rows]


def dequeue_request(request_id: str) -> bool:
    """Remove a processed job from the queue. Returns True if a row was deleted."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM queue WHERE request_id = ?", (request_id,))
        return cur.rowcount > 0


# --- magic links ---

def create_magic_link(email: str, request_id: str = None) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_TTL_MINUTES)).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO magic_links (token, email, expires_at, request_id) VALUES (?, ?, ?, ?)",
            (token, email, expires_at, request_id),
        )
    return token


def consume_magic_link(token: str) -> str | None:
    """Validate and consume a magic link token. Returns the email or None if invalid/expired/used.
    If the token is tied to a request_id, that request is marked verified."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT email, expires_at, used, request_id FROM magic_links WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        if row["used"]:
            return None
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            return None
        conn.execute("UPDATE magic_links SET used = 1 WHERE token = ?", (token,))
        if row["request_id"]:
            conn.execute(
                "UPDATE queue SET verified = 1 WHERE request_id = ?",
                (row["request_id"],),
            )
        return row["email"]


if __name__ == "__main__":
    init_db()
    print("Database initialised:", DB_PATH)
