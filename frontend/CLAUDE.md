# StreetScanner Frontend

## Stack

| Concern | Library |
| --- | --- |
| Framework | React 18 + TypeScript |
| Build | Vite |
| Components | Mantine v7 |
| Server state / polling | TanStack Query v5 |
| Routing | React Router v7 |
| HTTP client | fetch (native) — no extra lib needed |

---

## Backend API design

Base path: `/api`

All responses are JSON. Errors return `{ "error": "message" }` with an appropriate HTTP status.

---

### Reference data

#### `GET /api/cities`

Returns the list of cities available for route selection.

```json
{
  "cities": [
    { "id": "boston", "name": "Boston" },
    { "id": "new-york", "name": "New York" }
  ]
}
```

Used by: the job submission form's origin/destination dropdowns.

---

### Jobs

#### `POST /api/jobs`

Submit a new job (public-facing form).

Request body:

```json
{
  "email": "user@example.com",
  "origin_city": "new-york",
  "dest_city": "boston",
  "days": ["Fri", "Sat"]
}
```

Response `201`:

```json
{ "request_id": "550e8400-e29b-41d4-a716-446655440000" }
```

Validation failures return `400`. Unknown city IDs return `422`.

---

#### `GET /api/jobs`

Paginated list of all jobs. Admin dashboard — jobs queue tab.

Query params: `?page=1&limit=20`

```json
{
  "jobs": [
    {
      "request_id": "550e8400-...",
      "email": "user@example.com",
      "origin_city": "New York",
      "dest_city": "Boston",
      "days": ["Fri", "Sat"],
      "submit_time": "2026-05-02T14:00:00"
    }
  ],
  "total": 42,
  "page": 1,
  "limit": 20
}
```

---

#### `DELETE /api/jobs/:request_id`

Remove a job from the queue. Admin only.

Response `204` on success, `404` if not found.

---

### Email queue

#### `GET /api/email-queue`

Paginated email queue. Admin dashboard — email queue tab.

Query params: `?status=pending|sent|all&page=1&limit=20`

Default `status=all`.

```json
{
  "emails": [
    {
      "id": 1,
      "request_id": "550e8400-...",
      "email": "user@example.com",
      "subject": "Bus prices: New York → Boston | May 2 – May 30",
      "created_at": "2026-05-02T14:05:00",
      "sent_at": null
    }
  ],
  "total": 7,
  "page": 1,
  "limit": 20
}
```

`sent_at: null` means pending.

---

#### `GET /api/email-queue/:id/preview`

Returns the raw HTML body of a queued email — used to render an iframe preview
in the admin dashboard.

Response: `text/html`

---

### Logs

#### `GET /api/logs`

Paginated log entries written by the job fulfiller. Displayed as a tab inside
the admin dashboard.

Query params: `?level=error|warning|info|all&page=1&limit=50`

Default `level=all`.

```json
{
  "logs": [
    {
      "id": 7,
      "created_at": "2026-05-02T14:06:01",
      "level": "error",
      "company": "greyhound",
      "request_id": "550e8400-...",
      "message": "got a non-200 from upstream (HTTP 503)"
    }
  ],
  "total": 31,
  "page": 1,
  "limit": 50
}
```

---

### Stats (dashboard summary cards)

#### `GET /api/stats`

Cheap aggregate counts for the top-of-dashboard summary row.

```json
{
  "jobs_total": 42,
  "emails_pending": 3,
  "emails_sent": 18,
  "errors_24h": 5
}
```

TanStack Query should poll this every 10s on the dashboard.

---

## Frontend pages / routes

| Route | Component | Notes |
| --- | --- | --- |
| `/` | `SubmitJob` | Public form — city dropdowns, day picker, email field |
| `/auth/login` | `Login` | "Sign in with GitHub" button |
| `/auth/callback` | — | Handled server-side, redirects to `/admin` on success |
| `/admin` | `Dashboard` | Tabs: Jobs, Email Queue, Logs. Default tab: Jobs |
| `/admin/email-queue/:id/preview` | `EmailPreview` | iframe rendering the HTML body |

The admin dashboard is a single page with four tabs:

- **Jobs** — paginated table of all jobs, polling every 10s, delete action per row
- **Email Queue** — paginated table with pending/sent filter, polling every 10s
- **Logs** — paginated table with level filter (all / error / warning / info), polling every 30s
- **Stats** — summary cards at the top, always visible regardless of active tab

---

## Authentication

Admin routes (`/admin/*` and the admin API endpoints) are protected via GitHub OAuth.

### Flow

1. Unauthenticated request to `/admin/*` → redirect to `/auth/login`
2. User clicks "Sign in with GitHub" → server redirects to GitHub OAuth
3. GitHub redirects to `/auth/callback?code=...`
4. Server exchanges code for access token, fetches `https://api.github.com/user`
5. Checks returned `login` against `GITHUB_ALLOWED_USERS` in `.env`
6. On success: sets a signed session cookie, redirects to `/admin`
7. On failure (user not in allowlist): redirects to `/auth/login?error=unauthorized`

### Backend library

Use **Authlib** (works with both Flask and FastAPI) or **Flask-Dance** (simpler,
Flask-only, has a pre-built GitHub blueprint).

### Session storage

A signed cookie via Flask's built-in `session` is sufficient — no database
session table needed at this scale. Requires `FLASK_SECRET_KEY` to be set.

### Required `.env` variables

```env
GITHUB_CLIENT_ID=        # from your GitHub OAuth app settings
GITHUB_CLIENT_SECRET=    # from your GitHub OAuth app settings
GITHUB_ALLOWED_USERS=trentwiles  # comma-separated GitHub usernames
FLASK_SECRET_KEY=        # random string, used to sign session cookies
```

Register the OAuth app at: GitHub → Settings → Developer settings → OAuth Apps

- Homepage URL: `http://localhost:5000` (update for production)
- Callback URL: `http://localhost:5000/auth/callback` (update for production)

### Production note

GitHub OAuth requires the callback URL to use HTTPS in production.
Locally, `http://localhost` works without TLS.

---

## Notes

- `days` is stored as a comma-separated string in SQLite (`"Fri,Sat"`) — the API
  should serialize it as a proper array (`["Fri", "Sat"]`) in both directions.
- `html_body` is never returned in list responses — only via the `/preview` endpoint,
  to keep list payloads small.
- All `/api/jobs` (GET, DELETE), `/api/email-queue`, and `/api/logs` endpoints
  require an active session — return `401` if the session cookie is missing or invalid.
