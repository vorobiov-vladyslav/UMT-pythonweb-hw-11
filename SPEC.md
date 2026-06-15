# UMT-pythonweb-hw-11 — Specification

## 1. Goal

Extend the existing **contacts REST API** (from `UMT-pythonweb-hw-08`) with
user accounts and the security / infrastructure features taught in Topics
9–11:

- **Authentication** — register + log in users; passwords hashed, never stored
  in clear text.
- **Authorization** — protect every contact operation with a **JWT
  `access_token`**, refreshed via a long-lived **`refresh_token`** (access +
  refresh token pair).
- **Ownership isolation** — a user can only see and mutate **their own**
  contacts.
- **Email verification** — confirm a newly registered user's email via a
  signed link.
- **Rate limiting** — cap requests to the `/me` route.
- **CORS** — enable cross-origin access to the API.
- **Avatar upload** — let a user replace their avatar via **Cloudinary**.

This is a learning exercise. Scope is the homework rubric (15 pts) plus
keeping the existing contacts CRUD, search, birthdays, Docker packaging, the
4-layer architecture, and the test suite green. Nothing beyond that.

> **Base of work**: this spec assumes the `UMT-pythonweb-hw-08` codebase as
> the starting point (clone it, rename to `UMT-pythonweb-hw-11`, then apply the
> changes below). Everything in hw-08's `SPEC.md` still holds except where this
> document overrides it.

## 2. Stack decision — sync, not async

The hw-08 base uses **synchronous** SQLAlchemy 2.0 (`Session`,
`SessionLocal`, `psycopg[binary]` v3, `get_db()` generator). The Topic 9–11
lecture snippets are written **async** (`AsyncSession`, `asyncpg`, `async def`
repository methods).

**Decision: keep the existing synchronous stack.** Rewriting the whole app to
async would be a large, risky change unrelated to what this homework grades.
Every Topic 9–11 building block has a direct synchronous equivalent:

| Lecture (async) | This project (sync) |
|-----------------|---------------------|
| `async def` repo methods on `AsyncSession` | sync methods on `Session` (as in hw-08) |
| `passlib[bcrypt]` `CryptContext` | replaced with `pwdlib` (argon2) — also sync; see note below |
| `python-jose` `jwt.encode/decode` | identical — pure CPU, sync |
| `slowapi` `@limiter.limit(...)` | identical — works on sync routes |
| `cloudinary.uploader.upload` | identical — sync HTTP call |
| `fastapi-mail` `await fm.send_message(...)` | called inside a `BackgroundTasks` task (FastAPI awaits async background tasks even from a sync route) |

The only inherently-async piece, `fastapi-mail`, runs as a background task,
so the request handlers stay synchronous. Where this spec quotes lecture code,
treat it as illustrative — implement it sync, mirroring hw-08's layering.

## 3. Tech stack — additions

Everything from hw-08 §2 stays. **New** runtime dependencies:

| Concern               | Choice                                              |
|-----------------------|-----------------------------------------------------|
| Password hashing      | **`pwdlib[argon2]`** (`PasswordHash.recommended()` → argon2id). The lecture uses `passlib[bcrypt]`, but passlib is unmaintained and breaks with `bcrypt>=4.1`; pwdlib is the maintained successor FastAPI's own docs moved to. The rubric only requires hashing, not a specific algorithm. |
| JWT                   | **`python-jose[cryptography]`** (`HS256`)           |
| OAuth2 password flow  | `fastapi.security.OAuth2PasswordBearer` / `OAuth2PasswordRequestForm` |
| Email                 | **`fastapi-mail`** (SMTP via `smtp.meta.ua`, Jinja2 templates) |
| Rate limiting         | **`slowapi`** (in-memory token bucket)              |
| Cloud media           | **`cloudinary`**                                    |
| Default avatar        | **`libgravatar`** (Gravatar URL on registration)    |

Install: `uv add "python-jose[cryptography]" "pwdlib[argon2]" fastapi-mail slowapi cloudinary libgravatar python-multipart`

Repo name on GitHub: **`UMT-pythonweb-hw-11`** (public).

## 4. Data model changes

### 4.1 New table `users`

| Column          | Type           | Constraints                          | Notes                              |
|-----------------|----------------|--------------------------------------|------------------------------------|
| `id`            | `INTEGER`      | PK, autoincrement                    |                                    |
| `username`      | `VARCHAR(50)`  | NOT NULL, UNIQUE                     | display name, used in emails       |
| `email`         | `VARCHAR(120)` | NOT NULL, UNIQUE, indexed            | login identity; Pydantic-validated |
| `hashed_password` | `VARCHAR(255)` | NOT NULL                           | argon2id hash — never the raw password |
| `avatar`        | `VARCHAR(255)` | NULL                                 | Gravatar URL by default, Cloudinary after upload |
| `confirmed`     | `BOOLEAN`      | NOT NULL, default `false`            | set `true` after email verification |
| `refresh_token` | `VARCHAR(255)` | NULL                                 | the user's current refresh token (single-device; DB-checked so it can be revoked) |
| `created_at`    | `TIMESTAMP`    | NOT NULL, server default `now()`     | bookkeeping                        |

### 4.2 `contacts` table — add ownership

- Add `user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE`,
  indexed.
- **Change** the `email` uniqueness: drop the **global** `UNIQUE(email)` and
  replace it with a **composite** `UNIQUE(user_id, email)` named
  `uq_contacts_user_email`. Rationale: two different users may legitimately
  store a contact with the same email; uniqueness only matters within one
  user's address book.
- Add `user = relationship("User", backref="contacts")`.

### 4.3 Migration note (fresh DB)

Existing `contacts` rows have no owner, so adding a `NOT NULL` `user_id` to a
populated table can't be auto-filled. For this learning project the accepted
path is a **fresh database**: `docker compose down -v` then re-migrate.
(Production would backfill via a nullable column → data migration → `NOT
NULL`; out of scope here — document the choice in the migration message.)

Two Alembic revisions (or one combined), autogenerated then reviewed:

1. `create users table`
2. `add user_id to contacts and per-user email uniqueness`

## 5. Pydantic schemas — additions (`src/schemas.py`)

```text
UserCreate
  username: str        (1..50, stripped, non-empty)
  email:    EmailStr
  password: str        (min_length=6, max_length=128)

UserResponse              # safe to return — no password hash
  id: int
  username: str
  email: EmailStr
  avatar: str | None
  confirmed: bool
  created_at: datetime
  model_config = ConfigDict(from_attributes=True)

Token                     # returned by login and by refresh
  access_token: str
  refresh_token: str
  token_type: str = "bearer"

TokenRefreshRequest       # body of POST /api/auth/refresh_token
  refresh_token: str

RequestEmail              # for "resend verification"
  email: EmailStr
```

Existing `Contact{Base,Create,Update,Read}` are unchanged. `user_id` is **not**
exposed in `ContactCreate`/`ContactUpdate` — it's taken from the authenticated
user server-side, never from the request body.

## 6. API surface

### 6.1 Auth router — `src/api/auth.py`, prefix `/api/auth`, tag `auth`

| Method | Path                              | Purpose                                   | Success | Errors                       |
|--------|-----------------------------------|-------------------------------------------|---------|------------------------------|
| POST   | `/api/auth/register`              | Register a user; send verification email  | **201** | 409 (email/username taken), 422 |
| POST   | `/api/auth/login`                 | Authenticate; issue access + refresh token | 200    | 401 (bad creds / not confirmed) |
| POST   | `/api/auth/refresh_token`         | Exchange a valid refresh token for a new pair | 200 | 401 (bad/expired/revoked refresh) |
| GET    | `/api/auth/confirmed_email/{token}` | Confirm email from the link             | 200     | 400 (bad/expired token), 401 |
| POST   | `/api/auth/request_email`         | Re-send the verification email            | 200     | 422                          |

- **`register`** — body `UserCreate`. If `email` (or `username`) already
  exists → **409 Conflict**. Otherwise: hash the password, compute a Gravatar
  URL for `avatar`, persist (`confirmed=False`), enqueue the verification
  email as a `BackgroundTasks` task, return **201** + `UserResponse`.
- **`login`** — accepts **`OAuth2PasswordRequestForm`** (form fields
  `username`, `password`). **The `username` field carries the user's email**
  (we log in by email). Look up by email; if missing or
  `verify_password` fails → **401 Unauthorized** (`"Invalid credentials"`). If
  the user is not `confirmed` → **401** (`"Email not confirmed"`). Otherwise
  mint an **access token** and a **refresh token**, **persist the refresh token
  on the user row** (`UserService.update_refresh_token`), and return the
  `Token` pair.
- **`refresh_token`** — body `TokenRefreshRequest`. Validate via
  `verify_refresh_token` (§7): decode, require `token_type == "refresh"`, and
  confirm it equals the value stored on the user row (so a rotated/revoked
  token is rejected). On failure → **401**. On success, mint a **new pair**,
  store the new refresh token (rotation), and return it.
- **`confirmed_email`** — decode the email token (`sub` = email). If valid and
  the user exists: if already confirmed return `{"message": "Email already
  confirmed"}`; else set `confirmed=True` and return `{"message": "Email
  confirmed"}`. Invalid/expired token → 422/400.
- **`request_email`** — body `RequestEmail`; if the user exists and is not yet
  confirmed, re-enqueue the verification email. Always responds 200 with a
  generic message (don't leak which emails are registered).

### 6.2 Users router — `src/api/users.py`, prefix `/api/users`, tag `users`

| Method | Path                | Purpose                          | Success | Errors            |
|--------|---------------------|----------------------------------|---------|-------------------|
| GET    | `/api/users/me`     | Current user's profile           | 200     | 401, **429**      |
| PATCH  | `/api/users/avatar` | Upload/replace avatar (Cloudinary) | 200   | 401, 422          |

- **`/me`** — returns `UserResponse` for `Depends(get_current_user)`.
  **Rate-limited** (see §9).
- **`/avatar`** — `file: UploadFile = File(...)`, `user = Depends(get_current_user)`.
  Upload to Cloudinary, save the returned URL on the user, return
  `UserResponse`.

### 6.3 Contacts router — now protected & owner-scoped

Every existing contacts endpoint (`POST/GET/GET birthdays/GET {id}/PUT/DELETE`
under `/api/contacts`) gains `current_user: User = Depends(get_current_user)`.

- Unauthenticated request → **401** (handled by `OAuth2PasswordBearer`).
- All reads and writes are **scoped to `current_user.id`**. A contact owned by
  another user is treated as **non-existent** → **404** (never 403 — don't
  reveal that someone else's contact exists).
- On create, `user_id` is set from `current_user`, not the payload.
- Duplicate email now means "this user already has a contact with that email"
  → **409**.

Route-order rule from hw-08 still applies: `/contacts/birthdays` is declared
before `/contacts/{contact_id}`.

### 6.4 Healthcheck

`GET /api/healthchecker` stays public (no auth) — sanity only.

## 7. Authentication mechanics — `src/services/auth.py`

Mirrors the Topic 9 lecture, kept synchronous.

- `class Hash` wrapping `PasswordHash.recommended()` (pwdlib, argon2id) with
  `get_password_hash(password)` and `verify_password(plain, hashed)`.
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")`.
- `create_token(data: dict, expires_delta: timedelta, token_type: Literal["access","refresh"]) -> str`
  — copy `data`, add `iat`, `exp` (now + `expires_delta`), and a
  **`token_type`** claim, then `jwt.encode(..., settings.jwt_secret,
  algorithm=settings.jwt_algorithm)`. The `sub` claim is the user's **email**.
- `create_access_token(data)` — `create_token(..., access_expiry, "access")`;
  default expiry `settings.jwt_access_expiration_seconds` (3600 = 1 h).
- `create_refresh_token(data)` — `create_token(..., refresh_expiry, "refresh")`;
  default expiry `settings.jwt_refresh_expiration_seconds` (604800 = 7 days).
- `create_email_token(data)` — same encoder, **7-day** expiry, used only for
  email verification (no `token_type` needed).
- `get_email_from_token(token)` — decode, return `sub`; raise
  `HTTPException(422, "Invalid token for email verification")` on `JWTError`.
- `get_current_user(token = Depends(oauth2_scheme), db = Depends(get_db)) -> User`
  — decode JWT, **require `token_type == "access"`** (reject refresh tokens
  used as bearer), read `sub` (email), fetch the user; on any failure raise the
  standard **401** `"Could not validate credentials"` with
  `WWW-Authenticate: Bearer`.
- `verify_refresh_token(refresh_token: str, db: Session) -> User | None`
  — decode; require `token_type == "refresh"`; fetch the user by **both**
  `email == sub` **and** `refresh_token == <the token>` (DB match), so a
  rotated or revoked token fails. Return `None` on any mismatch / `JWTError`.

> **One identity key.** Access, refresh, and email tokens all use the user's
> **email** as `sub`, and lookups are by email. The `token_type` claim keeps
> the access and refresh tokens from being used in each other's place.

> **Why store the refresh token in the DB?** It lets the server *revoke* it:
> rotation on every refresh invalidates the previous one, and the DB check
> means a stolen refresh token stops working once the user logs in again or
> refreshes. Single-device only (one column); multi-device would need a
> separate `refresh_tokens` table — out of scope.

### Layering for auth

Follow hw-08's 4-layer split:

- **`src/repository/users.py`** — `UserRepository(Session)` with
  `get_by_id`, `get_by_email`, `get_by_username`, `create(username, email,
  hashed_password, avatar)`, `confirmed_email(email)`,
  `update_avatar_url(email, url)`, `update_refresh_token(email, token)`. Pure
  SQLAlchemy.
- **`src/services/users.py`** — `UserService(UserRepository)`: orchestrates
  registration (duplicate-check → `DuplicateUser`, hashing happens here or in
  the auth service), confirmation, avatar update.
- **`src/services/auth.py`** — the token/hash primitives + `get_current_user`
  dependency (above).
- **`src/services/deps.py`** — add `get_user_repository` / `get_user_service`
  factories alongside the existing contact ones.
- **`src/api/auth.py`**, **`src/api/users.py`** — thin HTTP handlers that
  translate domain exceptions to status codes.

New domain exceptions in `src/services/exceptions.py`:
`DuplicateUser` (→ 409), `UserNotFound` (→ used internally), reuse of the 401
pattern for credentials lives in the API/auth layer.

## 8. Email verification flow — `src/services/email.py`

- `ConnectionConfig` built entirely from `settings` (no secrets in code);
  `TEMPLATE_FOLDER = Path(__file__).parent / "templates"`.
- `send_verification_email(email, username, host)` — create an email token,
  build a `MessageSchema` (subtype HTML), `await fm.send_message(..., template_name="verify_email.html")`,
  swallow `ConnectionErrors` (log, don't crash the request).
- Template `src/services/templates/verify_email.html` (Jinja2) links to
  `{{host}}api/auth/confirmed_email/{{token}}`.
- Triggered from `register` (and `request_email`) via
  `background_tasks.add_task(send_verification_email, email, username, str(request.base_url))`.

## 9. Rate limiting — `slowapi`

- In `main.py`: `limiter = Limiter(key_func=get_remote_address)`,
  `app.state.limiter = limiter`, and register a `RateLimitExceeded` handler
  returning **429** with a JSON body (`{"error": "Rate limit exceeded. Try
  again later."}`).
- Decorate `GET /api/users/me` with `@limiter.limit("10/minute")`. The handler
  **must** take `request: Request` as a parameter (slowapi requires it).
- Document the limit in the route `description` so it shows in Swagger.

> Limit chosen: **10 requests / minute** on `/me`, matching the Topic 10
> lecture (the homework requirement names the route but not a number). Adjust
> via the decorator string if the grader expects a different value.

## 10. CORS

In `main.py`, add `CORSMiddleware`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # e.g. ["http://localhost:3000"]; "*" acceptable for the HW
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`cors_origins` comes from settings (default `["*"]` for the homework; a real
deployment would list explicit origins).

## 11. Avatar upload — Cloudinary — `src/services/upload_file.py`

- `UploadFileService(cloud_name, api_key, api_secret)` configures
  `cloudinary.config(..., secure=True)` in its constructor.
- `upload_file(file, username) -> str` — `cloudinary.uploader.upload(file.file,
  public_id=f"RestApp/{username}", overwrite=True)`, then build a 250×250
  `crop="fill"` URL via `cloudinary.CloudinaryImage(...).build_url(version=...)`.
- `PATCH /api/users/avatar` calls the service, then
  `UserService.update_avatar_url(user.email, url)`, returns `UserResponse`.

## 12. Configuration — `src/conf/config.py`

Extend the existing `Settings` (pydantic-settings) with new fields; **no
secrets in source** — all come from `.env`:

```text
# existing
database_url: str

# JWT
jwt_secret: str
jwt_algorithm: str = "HS256"
jwt_access_expiration_seconds: int = 3600       # 1 hour
jwt_refresh_expiration_seconds: int = 604800    # 7 days

# mail (smtp.meta.ua per the lecture)
mail_username: EmailStr
mail_password: str
mail_from: EmailStr
mail_port: int = 465
mail_server: str = "smtp.meta.ua"
mail_from_name: str = "Contacts API"
mail_starttls: bool = False
mail_ssl_tls: bool = True
use_credentials: bool = True
validate_certs: bool = True

# cloudinary
cloudinary_name: str
cloudinary_api_key: str
cloudinary_api_secret: str

# cors
cors_origins: list[str] = ["*"]
```

`.env.example` is updated with every new key (placeholder values); `.env` stays
gitignored. `docker-compose.yml` passes the same vars to the `api` service (or
mounts the `.env`).

## 13. Docker packaging

No structural change from hw-08 §12. Adjustments:

- The `api` service must receive all new env vars (extend the `environment:`
  block or add `env_file: .env`).
- Migrations still run as a one-shot: `docker compose run --rm api uv run
  alembic upgrade head`.
- Both run modes (full Docker / hybrid) from hw-08 §14 must keep working.

## 14. Tests — additions

Keep the hw-08 suite green (contacts CRUD / search / birthdays) — but those
endpoints now need an authenticated client, so fixtures must provide one.

New / updated fixtures in `tests/conftest.py`:
- `test_user` — a confirmed user persisted in the test DB.
- `auth_headers` — `{"Authorization": f"Bearer {access_token}"}` for `test_user`.
- `client` requests to `/api/contacts*` now send `auth_headers`.
- Override the email-send background task with a no-op/mock so tests never hit
  SMTP; override Cloudinary upload with a stub returning a fixed URL.

New test files:
- `tests/test_auth.py` — register returns 201 + body; duplicate email → 409;
  password is stored hashed (not equal to the raw); login returns an
  access+refresh pair and stores the refresh token; wrong password → 401;
  unconfirmed login → 401; `confirmed_email` flips the flag; bad token → 422;
  `refresh_token` returns a new pair; a refresh token used as a bearer on a
  protected route → 401 (`token_type` check); a stale/rotated refresh token →
  401.
- `tests/test_users.py` — `/me` returns the current user; `/me` without a token
  → 401; exceeding the rate limit → 429; `/avatar` updates the URL (Cloudinary
  stubbed).
- `tests/test_contacts_ownership.py` — user A cannot read/update/delete user
  B's contact (404); listing only returns the caller's contacts.

Update the existing `test_contacts_*` to use `auth_headers`.

## 15. Acceptance criteria — mapped to the 15-point rubric

| Pts | Criterion (homework)                                        | Where in this spec        |
|-----|-------------------------------------------------------------|---------------------------|
| 3   | Authentication mechanism                                    | §6.1 register/login, §7   |
| 3   | Authorization via JWT for all contact operations            | §6.3, §7                  |
| 2   | User accesses only their own contacts                       | §4.2, §6.3                |
| 3   | Email verification of the registered user                   | §6.1, §8                  |
| 1   | Rate limit on the `/me` route                               | §6.2, §9                  |
| 1   | CORS enabled                                                | §10                       |
| 2   | Avatar update via Cloudinary                                | §6.2, §11                 |
| **15** | **Total**                                                |                           |

### General requirements (pass/fail) — all covered

- Duplicate-email registration → **409** — §6.1.
- Password hashed, never stored in clear text — §4.1, §7.
- Successful registration → **201** + user data — §6.1.
- All create (`POST`) operations → **201** — §6.1, contacts POST (hw-08).
- Login authenticates the user from supplied credentials — §6.1.
- Unknown user / wrong password → **401** — §6.1.
- Authorization via JWT **`access_token`** — §7.
- All secrets in **`.env`**, none in source — §12.
- All services + DB run via **Docker Compose** — §13.

## 16. Out of scope

- Multi-device refresh tokens (a separate `refresh_tokens` table). We store a
  single refresh token per user (§4.1) — one device. The access+refresh pair
  itself **is** implemented (§6.1, §7), beyond the rubric's `access_token`
  minimum, for learning.
- Password reset flow (lecture mentions it; not in the rubric).
- Roles / permissions, IP/User-Agent blocking, response caching (Topic 10
  extras beyond rate-limit + CORS).
- Migrating the app to async SQLAlchemy (§2).
- Backfilling owners onto pre-existing contacts (§4.3 — fresh DB instead).
- Frontend, public deployment, CI/CD.

## 17. Submission checklist

- [ ] Public GitHub repo **`UMT-pythonweb-hw-11`**.
- [ ] `docker compose up -d --build` works from a clean clone; migrations apply
      to a fresh DB.
- [ ] `uv run pytest` is green (incl. new auth/users/ownership tests).
- [ ] Register → receive verification email → confirm → login → call protected
      contacts endpoints with the `access_token` — full happy path works.
- [ ] `/api/users/me` returns 429 after exceeding the limit.
- [ ] Avatar upload returns a Cloudinary URL.
- [ ] `.env` is gitignored; `.env.example` lists every key.
- [ ] `README.md` updated: new endpoints, env vars, auth flow, link to `/docs`.
- [ ] Zip the working tree as **`ДЗ11_ПІБ.zip`** and upload to LMS with the
      repo URL. *(LMS deadline shown: 23:45, 1 Jun — past as of 3 Jun 2026;
      confirm late-submission rules with the instructor.)*
