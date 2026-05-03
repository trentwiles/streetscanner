# StreetScanner — Architecture & Request Lifecycle

## Overview

StreetScanner is a price-tracking service for intercity bus routes. Users subscribe to a route and preferred travel days; the system periodically scrapes prices from four bus companies and emails a digest of the cheapest options.

The system has three independent components, each run separately (manually or via cron):

| Component | File | Role |
|---|---|---|
| API server | `app.py` | Accepts user subscriptions via HTTP |
| Job fulfiller | `jobFufil.py` | Scrapes prices and populates the email queue |
| Mailer | `mailer.py` | Drains the email queue one message at a time |

---

## Database Schema

Five tables in `streetscanner.db` (SQLite):

- **`cities`** — canonical city list (`id`, `city`)
- **`translations`** — maps each city to the identifier each bus API expects (UUID, plaintext, etc.)
- **`jobs`** — user subscriptions (one row per subscriber)
- **`email_queue`** — rendered HTML emails waiting to be sent
- **`logs`** — structured log output from `jobFufil.py`

---

## Request Lifecycle

### Stage 1 — User submits a subscription (`app.py`)

The React frontend posts to `POST /api/jobs` with:

```json
{ "email": "...", "origin_city": "<city_id>", "dest_city": "<city_id>", "days": ["Fri", "Sat"] }
```

`app.py` validates the input, resolves the city IDs against the `cities` table, and inserts a row into `jobs`:

```
request_id        — UUID (primary key)
email             — recipient address
originCity        — human city name (e.g. "New York")
destCity          — human city name (e.g. "Boston")
days              — comma-separated abbreviations e.g. "Fri,Sat,Sun"
submit_ip         — client IP
submit_time       — UTC ISO timestamp
submit_user_agent — browser UA string
```

The API returns `{ "request_id": "..." }` and is done. `app.py` has no further involvement.

Jobs are **never automatically deleted** — they are permanent subscriptions that produce a new email every time `jobFufil.py` runs.

---

### Stage 2 — Scraping and queuing (`jobFufil.py`)

Intended to run via cron on a recurring schedule (e.g. twice a week). Each run processes **all jobs** in the table.

**2a. Time estimate**

Before the loop, the script counts the jobs and logs an estimate to both stdout and the `logs` table:

```
3 job(s) queued; estimated runtime 30s–90s (sleep 10s–30s between jobs)
```

**2b. Date expansion**

For each job, `dates_for_days()` expands the `days` string into concrete `YYYY-MM-DD` dates over the next **4 weeks**. A job with `"Fri,Sat"` produces ~8 dates.

**2c. Multi-company search**

For each date, `search_all_companies()` queries all four bus APIs in sequence:

| Company | Identifier format | Script |
|---|---|---|
| Greyhound / Flixbus | UUID | `greyhound.py` |
| Peter Pan | UUID | `peterpan.py` |
| OurBus | Plaintext city name | `ourbus.py` |
| Coachrun | Internal identifier | `coachrun.py` |

Identifiers are looked up from the `translations` table at query time. If no translation exists for a company/city pair, that company is skipped for that route. Errors are caught per-company and written to `logs`; a failure on one company does not abort the others.

**2d. Normalization and rendering (`cleaner.py`)**

Raw scraper output varies by company. `cleaner.py` normalizes every trip into a canonical shape:

```
company, date, price (float), depart_time (HH:MM), arrive_time (HH:MM), duration
```

Trips with no price are discarded. The remaining trips are sorted by `(date, price)`.

`render_email_html()` passes the normalized trips into a Jinja2 template (`templates/email_digest.html`) which produces two sections:
- **Top 5 cheapest** across all dates
- **Per-date breakdown** sorted by price

The subject line is generated as e.g. `Bus prices: New York → Boston | May 2 – May 30`.

**2e. Queue insertion**

The rendered HTML, subject, and recipient email are inserted into `email_queue`:

```
request_id  — FK back to jobs
email       — recipient address
subject     — plain-text subject line
html_body   — fully rendered HTML
created_at  — UTC timestamp
sent_at     — NULL until delivered
```

One row is inserted per job per run. There is no deduplication — re-queuing is intentional so subscribers receive a fresh digest on each cron cycle.

**2f. Rate-limiting sleep**

After each job (except the last), the script sleeps for a random duration between `SLEEP_MIN` (10s) and `SLEEP_MAX` (30s) to avoid hammering the bus APIs in rapid succession.

---

### Stage 3 — Sending (`mailer.py`)

Intended to run via cron every 20 minutes, all day. Each invocation sends **at most one email**.

**3a. Time window check**

The script first checks the local system time. If it falls outside `05:30–08:00`, it exits immediately without touching the database. This gates all sends to a single early-morning window.

The window check is done in Python (not cron) because cron cannot express a `:30` start time precisely.

**3b. Pick oldest pending row**

```sql
SELECT * FROM email_queue WHERE sent_at IS NULL ORDER BY id LIMIT 1
```

FIFO order by insertion ID.

**3c. Send**

Opens an SMTP connection using credentials from `.env` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASS`). Sends the HTML email as a `multipart/alternative` MIME message.

**3d. Stamp or retry**

- **Success** — `sent_at` is stamped with the current UTC time. The row stays in the table as a permanent record.
- **Failure** — `sent_at` is left NULL. The row will be retried on the next cron invocation.

---

## Cron Schedule (recommended)

```cron
# Re-scrape all jobs and queue fresh emails — Monday and Thursday at midnight
0 0 * * 1,4 cd /path/to/streetscanner && .venv/bin/python jobFufil.py >> /tmp/jobfufil.log 2>&1

# Send one queued email every 20 min (window enforced inside the script)
*/20 * * * * cd /path/to/streetscanner && .venv/bin/python mailer.py >> /tmp/mailer.log 2>&1
```

At 20-minute intervals, the 5:30–8:00 window yields **7 send slots per morning**. With two scrape runs per week, the queue grows by N emails twice a week and drains at up to 7/day.

---

## Admin Panel

`app.py` exposes a set of authenticated REST endpoints (GitHub OAuth, allowlisted by username) used by the React admin frontend:

| Endpoint | Purpose |
|---|---|
| `GET /api/jobs` | Paginated job list |
| `DELETE /api/jobs/:id` | Remove a subscription |
| `GET /api/email-queue` | Paginated queue (filterable by sent/pending) |
| `GET /api/email-queue/:id/preview` | Render queued HTML in browser |
| `DELETE /api/email-queue/:id` | Remove a queued email (optionally also deletes the parent job) |
| `GET /api/logs` | Paginated log viewer (filterable by level) |
| `DELETE /api/logs` | Clear all logs |
| `GET /api/stats` | Dashboard counters (jobs total, emails pending/sent, errors in last 24h) |
