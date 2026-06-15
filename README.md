# UMT-pythonweb-hw-11

REST API for managing personal contacts, with user accounts, JWT auth, email
verification, request rate limiting, CORS, and Cloudinary avatar uploads.
FastAPI + SQLAlchemy 2.0 + PostgreSQL 16, packaged with Docker Compose.

Builds on `UMT-pythonweb-hw-08` (the contacts CRUD) — every contact now belongs
to a user and the endpoints are protected.

## API surface

### Auth — `/api/auth`

| Method | Path                                | Notes                                                       |
|--------|-------------------------------------|-------------------------------------------------------------|
| POST   | `/api/auth/register`                | Create user. **201** / 409 (email or username taken) / 422. Sends a verification email. |
| POST   | `/api/auth/login`                   | Form `username` (= email) + `password`. Returns access + refresh tokens. 401 on bad creds or unconfirmed email. |
| POST   | `/api/auth/refresh_token`           | Body `{refresh_token}`. Returns a new pair (rotates). 401 if invalid/rotated. |
| GET    | `/api/auth/confirmed_email/{token}` | Confirm email from the link. |
| POST   | `/api/auth/request_email`           | Body `{email}`. Re-sends the verification email. |

### Users — `/api/users` (auth required)

| Method | Path                | Notes                                                       |
|--------|---------------------|-------------------------------------------------------------|
| GET    | `/api/users/me`     | Current user. **Rate limited to 10 requests/minute** → 429. |
| PATCH  | `/api/users/avatar` | Upload an avatar image (multipart `file`) to Cloudinary.    |

### Contacts — `/api/contacts` (auth required, scoped to the owner)

| Method | Path                          | Notes                                                                |
|--------|-------------------------------|----------------------------------------------------------------------|
| POST   | `/api/contacts`               | Create. 201 / 409 (duplicate email for this user) / 422.             |
| GET    | `/api/contacts`               | List + search by `first_name`, `last_name`, `email` (ILIKE). 200/422. |
| GET    | `/api/contacts/birthdays`     | Upcoming birthdays in the next `days` (default 7, 1..30). 200/422.   |
| GET    | `/api/contacts/{id}`          | Get one. 200 / 404 (incl. contacts owned by another user).           |
| PUT    | `/api/contacts/{id}`          | Full update. 200 / 404 / 409 / 422.                                  |
| DELETE | `/api/contacts/{id}`          | 204 / 404.                                                           |
| GET    | `/api/healthchecker`          | `SELECT 1` round-trip (public).                                      |

All contacts endpoints require `Authorization: Bearer <access_token>`; without
it they return 401. A contact owned by another user is reported as 404.

Interactive docs at `/docs`; OpenAPI JSON at `/openapi.json`.

## Configuration

All secrets live in `.env` (gitignored). Copy the template and fill it in:

```bash
cp .env.example .env
```

### Minimum to run locally

Only **`JWT_SECRET`** has no default, so it's the one value you must set to boot
the app. Everything else has a working default for local dev (mail and Cloudinary
just won't do real network calls until you supply real credentials).

```bash
# generate a strong secret and paste it into JWT_SECRET
openssl rand -hex 32
```

So a minimal local `.env` is just:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:hw11secret@localhost:5433/hw11
JWT_SECRET=<paste output of `openssl rand -hex 32`>
```

With that, registration/login/JWT/contacts all work. The verification email is
sent as a background task and silently no-ops if SMTP isn't reachable — during
development you can confirm an account without real mail (see note below).

### All variables

| Variable | Required | Default | What it is / where to get it |
|---|---|---|---|
| `DATABASE_URL` | no | `...@localhost:5433/hw11` | SQLAlchemy URL. Use `localhost:5433` for host runs; Docker overrides it to `@postgres:5432` automatically. |
| `JWT_SECRET` | **yes** | — | Signing key for all JWTs. Generate with `openssl rand -hex 32`. |
| `JWT_ALGORITHM` | no | `HS256` | JWT signing algorithm. |
| `JWT_ACCESS_EXPIRATION_SECONDS` | no | `3600` (1 h) | Access-token lifetime. |
| `JWT_REFRESH_EXPIRATION_SECONDS` | no | `604800` (7 d) | Refresh-token lifetime. |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | for real email | meta.ua sample | SMTP login. Create a mailbox on [meta.ua](https://meta.ua) and enable POP3/SMTP access in its settings. |
| `MAIL_FROM` | for real email | `example@meta.ua` | "From" address (usually = `MAIL_USERNAME`). |
| `MAIL_SERVER` / `MAIL_PORT` | no | `smtp.meta.ua` / `465` | SMTP host/port. |
| `MAIL_FROM_NAME` | no | `Contacts API` | Display name on the email. |
| `MAIL_STARTTLS` / `MAIL_SSL_TLS` | no | `False` / `True` | TLS mode (meta.ua uses SSL on 465). |
| `CLOUDINARY_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | for avatar upload | placeholders | From your [Cloudinary](https://cloudinary.com) Dashboard → *Product Environment Credentials*. The free tier is enough. |
| `CORS_ORIGINS` | no | `["*"]` | JSON list of allowed origins, e.g. `["http://localhost:3000"]`. |

> **Confirming an account without real SMTP.** The confirmation link is
> `…/api/auth/confirmed_email/{token}`, where `{token}` is a JWT signed with your
> `JWT_SECRET`. In dev you can mint it yourself and hit that endpoint — e.g. in a
> Python shell: `from services.auth import create_email_token;
> create_email_token({"sub": "you@example.com"})` — then
> `GET /api/auth/confirmed_email/<token>`.

> **Ports.** This project maps Postgres to host **5433** and the API to host
> **8001** (the standard 5432/8000 were occupied on the dev machine). Change
> the `ports:` in `docker-compose.yml` if you prefer the defaults.

## Setup

### Mode A — full Docker (recommended for graders)

```bash
cp .env.example .env                       # then set JWT_SECRET
docker compose up -d --build
docker compose run --rm api uv run alembic upgrade head
open http://localhost:8001/docs            # interactive docs

docker compose logs -f api                 # tail logs
docker compose down                        # stop, keep DB volume
docker compose down -v                     # stop + drop DB volume
```

### Mode B — hybrid (Postgres in Docker, API on host, fastest dev loop)

```bash
docker compose up -d postgres
uv sync
uv run alembic upgrade head
PYTHONPATH=src uv run uvicorn main:app --reload   # serves on :8000
```

`PYTHONPATH=src` is required because `main.py` lives at the project root and
imports `api`, `services`, etc. as top-level modules. (Inside Docker the same
is set via `ENV PYTHONPATH=/app/src`.)

## Auth flow (quick walk-through)

```bash
BASE=http://localhost:8001

# 1. register
curl -X POST $BASE/api/auth/register -H "Content-Type: application/json" \
  -d '{"username":"ada","email":"ada@example.com","password":"pass1234"}'

# 2. confirm — click the link in the email, or call the endpoint with the token
curl "$BASE/api/auth/confirmed_email/<token-from-email>"

# 3. login (form-encoded; username field carries the email)
curl -X POST $BASE/api/auth/login \
  -d "username=ada@example.com&password=pass1234"
# -> {"access_token":"...","refresh_token":"...","token_type":"bearer"}

# 4. call protected endpoints
TOKEN=<access_token>
curl $BASE/api/users/me -H "Authorization: Bearer $TOKEN"
curl -X POST $BASE/api/contacts -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Grace","last_name":"Hopper","email":"grace@example.com",
       "phone":"+1","birthday":"1906-12-09"}'

# 5. refresh when the access token expires
curl -X POST $BASE/api/auth/refresh_token -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

## Tests

```bash
uv run pytest
```

The first run creates the `hw11_test` database automatically (against the
`postgres` maintenance DB) and applies the schema via SQLAlchemy `create_all`.
Each test runs inside a SAVEPOINT-wrapped transaction rolled back at teardown,
so repo-level commits don't leak between tests. SMTP and Cloudinary are stubbed;
the rate limiter is reset between tests.

## Architecture

Four-layer separation per entity (see `SPEC.md`):

```
src/api/{auth,users,contacts}.py        — HTTP / Pydantic / HTTPException
src/services/{auth,users,contacts}.py   — domain rules, tokens, exception translation
src/services/{email,upload_file}.py     — fastapi-mail, Cloudinary
src/repository/{users,contacts}.py      — SQLAlchemy queries
src/database/{db,models}.py             — engine, session, ORM (User, Contact)
src/schemas.py                          — Pydantic in/out
src/conf/{config,limiter}.py            — pydantic-settings, slowapi limiter
```

Identity is keyed on **email**: the `sub` claim of every JWT is the email, and
`get_current_user` looks the user up by it. Access tokens carry `token_type:
access`; refresh tokens carry `token_type: refresh` and are stored on the user
row so they can be rotated and revoked.

## Tech stack

- **FastAPI** + Uvicorn, **SQLAlchemy 2.0** (typed, sync session), **PostgreSQL 16**
- **Pydantic v2** + `pydantic[email]`, **Alembic** migrations
- **python-jose** (JWT), **pwdlib[argon2]** (argon2id) for password hashing
- **fastapi-mail** (verification email), **slowapi** (rate limit), **cloudinary**
  (avatars), **libgravatar** (default avatar)
- **pytest** + `httpx` TestClient, **uv** (lockfile committed), **ruff** + pre-commit
- Python `>=3.10` (Docker image `python:3.12-slim`)
