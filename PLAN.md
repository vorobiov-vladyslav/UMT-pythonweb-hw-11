# UMT-pythonweb-hw-11 — Implementation Plan

This plan turns `SPEC.md` into small, reviewable steps that extend the
`UMT-pythonweb-hw-08` contacts API with users, JWT auth, email verification,
rate limiting, CORS, and Cloudinary avatars. Each step is sized for a readable
diff and carries a short "FastAPI note" for the framework concept it
introduces.

## How to use this plan

- Tick `[x]` when a step is reviewed, committed, and pushed.
- One commit per step is the recommended cadence; the step title is a fine
  commit message.
- Don't skip ahead — models/migrations/config set up context later steps need.
- The whole app stays **synchronous** (SPEC §2). Treat the async lecture
  snippets as illustrative and implement them sync, mirroring hw-08's layering.

## Decisions (locked in)

- Base = clone of `UMT-pythonweb-hw-08`, renamed to `UMT-pythonweb-hw-11`.
- Sync SQLAlchemy (`Session`), not async.
- Login identity = **email** (carried in the OAuth2 form's `username` field);
  JWT `sub` = email.
- **Access + refresh token pair** (beyond the rubric, for learning). Refresh
  token stored on the `User` row, rotated on every refresh, DB-checked so it
  can be revoked. Single device. `token_type` claim distinguishes the two.
- Login is **blocked until the email is confirmed** → 401.
- Rate limit on `/me` = **10/minute** (lecture value; requirement gives none).
- Keep a `username` field on `User` (lecture-consistent; used in emails).
- Fresh DB for migrations (no owner backfill on existing contacts).

---

## Phase 0 — Bootstrap from hw-08

### [ ] 0.1 Clone and re-baseline the repo

- Create a public GitHub repo `UMT-pythonweb-hw-11`.
- Copy the hw-08 working tree (without `.git`) into the new project; set
  `origin` to the new repo. First commit: the unchanged hw-08 app + this
  `SPEC.md` / `PLAN.md`.
- Sanity: `uv sync`, `docker compose up -d postgres`, `uv run pytest` — the
  inherited suite must be green before any change.

**Why**: start from a known-good baseline so every later diff is attributable
to one feature.

### [ ] 0.2 Add the new dependencies

- `uv add "python-jose[cryptography]" "pwdlib[argon2]" fastapi-mail slowapi cloudinary libgravatar python-multipart`
- Commit the updated `pyproject.toml` + `uv.lock`.

**FastAPI note**: none of these are FastAPI itself — they're the auth (jose,
pwdlib), mail (fastapi-mail), rate-limit (slowapi), and media (cloudinary)
building blocks the routes will lean on.

### [ ] 0.3 Rename project identifiers

- `pyproject.toml` `name` → `umt-pythonweb-hw-11`; `FastAPI(title=...)`,
  compose container names, DB name (`hw11`), volume (`hw11-pgdata`),
  `.env.example` default `DATABASE_URL`.

**Why**: keeps the new homework self-contained and graders unconfused.

---

## Phase 1 — Configuration

### [ ] 1.1 Extend `Settings` (`src/conf/config.py`)

- Add the JWT, mail, cloudinary, and CORS fields from SPEC §12. Keep
  `extra="ignore"` and `.env` loading.
- Use sensible defaults only for non-secret fields (`jwt_algorithm`,
  `jwt_access_expiration_seconds`, `jwt_refresh_expiration_seconds`,
  `mail_port`, `mail_server`, `cors_origins`).
  Secrets (`jwt_secret`, `mail_password`, `cloudinary_*`) have **no** default —
  they must come from `.env`.

**FastAPI note**: `pydantic-settings` validates env at startup, so a missing
secret fails fast and loudly instead of surfacing as a 500 mid-request.

### [ ] 1.2 Update `.env.example` (and your local `.env`)

- Add every new key with placeholder values. Confirm `.env` is gitignored.

**Why**: the rubric requires all secrets in `.env`, none in source.

---

## Phase 2 — Data model & migrations

### [ ] 2.1 Add the `User` model (`src/database/models.py`)

- `User` per SPEC §4.1 using SQLAlchemy 2.0 `Mapped[...]` style (match hw-08's
  `Contact`): `username` (unique), `email` (unique, indexed),
  `hashed_password`, `avatar` (nullable), `confirmed` (default False),
  `refresh_token` (nullable), `created_at` (server default `now()`).

### [ ] 2.2 Add ownership to `Contact`

- Add `user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)`.
- Replace the column-level `unique=True` on `email` with a table-level
  `UniqueConstraint("user_id", "email", name="uq_contacts_user_email")`; keep
  `index=True` on `email`.
- Add `user = relationship("User", backref="contacts")`.

**FastAPI note**: nothing FastAPI here — pure SQLAlchemy. The FK + composite
unique is what makes contacts per-user.

### [ ] 2.3 Generate and apply migrations

- `docker compose down -v` (fresh DB — SPEC §4.3).
- `uv run alembic revision --autogenerate -m "create users table"` then a
  second `-m "add user_id and per-user email uniqueness to contacts"` (or one
  combined). **Review** the generated SQL against SPEC §4.
- `uv run alembic upgrade head`; verify with `\d users` and `\d contacts`.

**FastAPI note**: still the SQLAlchemy→Postgres bridge; FastAPI is uninvolved.

---

## Phase 3 — Schemas

### [ ] 3.1 Add user/auth schemas (`src/schemas.py`)

- `UserCreate`, `UserResponse` (`from_attributes=True`, no password hash),
  `Token`, `RequestEmail` per SPEC §5.
- Leave the `Contact*` schemas unchanged; `user_id` is never in a request body.

**FastAPI note**: `UserResponse` as the `response_model` guarantees the
password hash can never leak in a response, even if the handler returns the
full ORM object.

---

## Phase 4 — User data layer

### [ ] 4.1 `UserRepository` (`src/repository/users.py`)

- Constructor takes a `Session`. Methods: `get_by_id`, `get_by_email`,
  `get_by_username`, `create(username, email, hashed_password, avatar)`,
  `confirmed_email(email)`, `update_avatar_url(email, url)`,
  `update_refresh_token(email, token)`. Pure SQLAlchemy, sync, commit in the
  repo (consistent with hw-08's `ContactRepository`).

### [ ] 4.2 Domain exceptions

- Add `DuplicateUser` (and, if useful, `UserNotFound`) to
  `src/services/exceptions.py`.

### [ ] 4.3 `UserService` (`src/services/users.py`)

- Constructor takes a `UserRepository`. Methods:
  `register(username, email, password)` (duplicate-check by email/username →
  `DuplicateUser`; compute Gravatar avatar via `libgravatar`; hash password;
  create), `get_by_email`, `confirm(email)`, `update_avatar(email, url)`.

### [ ] 4.4 DI factories (`src/services/deps.py`)

- Add `get_user_repository(db=Depends(get_db))` and
  `get_user_service(repo=Depends(get_user_repository))`, alongside the existing
  contact factories.

**FastAPI note**: the `Depends` chain mirrors the contacts side — handlers ask
for `get_user_service`, FastAPI resolves repo → db automatically.

---

## Phase 5 — Auth service

### [ ] 5.1 Hash + token primitives (`src/services/auth.py`)

- `Hash` class (pwdlib `PasswordHash.recommended()` → argon2id,
  `get_password_hash`, `verify_password`).
- `create_token(data, expires_delta, token_type)` — unified encoder adding
  `iat`, `exp`, and a `token_type` claim (`"access"`/`"refresh"`); `jwt.encode`
  with `settings.jwt_secret` / `jwt_algorithm`.
- `create_access_token(data)` — `token_type="access"`, default expiry
  `settings.jwt_access_expiration_seconds`.
- `create_refresh_token(data)` — `token_type="refresh"`, default expiry
  `settings.jwt_refresh_expiration_seconds`.
- `verify_refresh_token(refresh_token, db)` — decode; require
  `token_type == "refresh"`; return the user only if `email == sub` **and**
  `User.refresh_token == refresh_token` in the DB; else `None`.
- `create_email_token(data)` — 7-day expiry (no `token_type`).
- `get_email_from_token(token)` — decode → `sub`; `JWTError` → 422.
- `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")`.

### [ ] 5.2 `get_current_user` dependency

- Decode the bearer token, **require `token_type == "access"`** (reject a
  refresh token used as a bearer), read `sub` (email), fetch the user via
  `UserService`/`UserRepository`; any failure → 401
  `"Could not validate credentials"` + `WWW-Authenticate: Bearer`.

**FastAPI note**: `OAuth2PasswordBearer` both parses the `Authorization:
Bearer` header and adds the "Authorize" button to Swagger. `get_current_user`
becomes the gate every protected route depends on.

---

## Phase 6 — Email verification

### [ ] 6.1 Email service (`src/services/email.py`) + template

- `ConnectionConfig` from `settings` (SPEC §8); `send_verification_email(email,
  username, host)` builds the token + `MessageSchema` and
  `await fm.send_message(..., "verify_email.html")`, swallowing
  `ConnectionErrors`.
- Add `src/services/templates/verify_email.html` linking to
  `{{host}}api/auth/confirmed_email/{{token}}`.

**FastAPI note**: `fastapi-mail` is async, but we only ever call it from a
`BackgroundTasks` task, so the request handlers stay sync and return
immediately.

---

## Phase 7 — Auth API

### [ ] 7.1 `POST /api/auth/register` (`src/api/auth.py`)

- Router `APIRouter(prefix="/auth", tags=["auth"])`, included under `/api`.
- `register(payload: UserCreate, request: Request, background_tasks: BackgroundTasks, service=Depends(get_user_service))`:
  `@router.post("/register", response_model=UserResponse, status_code=201)`.
- On `DuplicateUser` → `HTTPException(409, "Account already exists")`.
- On success: enqueue `send_verification_email(user.email, user.username, str(request.base_url))`.

**FastAPI note**: inject `BackgroundTasks` as a parameter and `add_task(...)`;
FastAPI runs it after the 201 response is sent.

### [ ] 7.2 `POST /api/auth/login`

- Param `form_data: OAuth2PasswordRequestForm = Depends()`. Treat
  `form_data.username` as the email.
- Look up by email; bad user/password → 401 `"Invalid credentials"`; not
  `confirmed` → 401 `"Email not confirmed"`.
- Mint both tokens (`create_access_token`/`create_refresh_token` with
  `{"sub": user.email}`), persist the refresh token
  (`UserService.update_refresh_token(user.email, refresh)`), and return
  `Token(access_token=..., refresh_token=..., token_type="bearer")`.

**FastAPI note**: `OAuth2PasswordRequestForm` reads `application/x-www-form-
urlencoded` (`username`/`password`) — that's what Swagger's Authorize dialog
posts.

### [ ] 7.3 `POST /api/auth/refresh_token`

- Body `TokenRefreshRequest`. Call `verify_refresh_token(body.refresh_token, db)`;
  `None` → 401 `"Invalid refresh token"`.
- On success: mint a **new** access+refresh pair, store the new refresh token
  (rotation), return the `Token`.

**FastAPI note**: this endpoint is unauthenticated by `get_current_user` on
purpose — the refresh token itself is the credential, validated against the DB.

### [ ] 7.4 `GET /api/auth/confirmed_email/{token}`

- Decode via `get_email_from_token`; fetch user; if already confirmed →
  `{"message": "Email already confirmed"}`; else `service.confirm(email)` →
  `{"message": "Email confirmed"}`.

### [ ] 7.5 `POST /api/auth/request_email`

- Body `RequestEmail`; if user exists and unconfirmed, re-enqueue the email.
  Always 200 with a generic message (don't reveal registration status).

### [ ] 7.6 Manual smoke test

- Register → check the inbox (or compose logs) → hit the confirm link → login →
  copy the `access_token` and `refresh_token` → call `/api/auth/refresh_token`
  and confirm a new pair comes back and the old refresh token stops working.

---

## Phase 8 — Users API (profile, rate limit, avatar)

### [ ] 8.1 `GET /api/users/me` with rate limiting (`src/api/users.py`)

- Router `APIRouter(prefix="/users", tags=["users"])`.
- `@router.get("/me", response_model=UserResponse, description="No more than 10 requests per minute")`,
  `@limiter.limit("10/minute")`, signature
  `def me(request: Request, user=Depends(get_current_user))`.
- Wire the shared `limiter` (Phase 9) — import it rather than creating a second
  instance.

**FastAPI note**: slowapi inspects the `request: Request` arg to read the
client IP via `key_func=get_remote_address`; omitting `request` raises at call
time.

### [ ] 8.2 Cloudinary upload service (`src/services/upload_file.py`)

- `UploadFileService(cloud_name, api_key, api_secret)` configures
  `cloudinary.config(secure=True)`; `upload_file(file, username)` uploads with
  `public_id=f"RestApp/{username}"`, returns a 250×250 `crop="fill"` URL.

### [ ] 8.3 `PATCH /api/users/avatar`

- `file: UploadFile = File(...)`, `user=Depends(get_current_user)`.
- Upload, then `UserService.update_avatar(user.email, url)`, return
  `UserResponse`.

**FastAPI note**: `UploadFile` streams the file via `file.file`; FastAPI parses
`multipart/form-data` automatically when a handler declares an `UploadFile`.

---

## Phase 9 — Cross-cutting: CORS + rate-limit wiring (`main.py`)

### [ ] 9.1 CORS middleware

- Add `CORSMiddleware` with `allow_origins=settings.cors_origins`,
  `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.

### [ ] 9.2 Rate-limit setup + handler

- `limiter = Limiter(key_func=get_remote_address)`; `app.state.limiter = limiter`.
- Register `@app.exception_handler(RateLimitExceeded)` returning **429** JSON.
- Put `limiter` somewhere importable by `api/users.py` (e.g. a small
  `src/conf/limiter.py` or pass via `app.state`); avoid two `Limiter`
  instances.

### [ ] 9.3 Include the new routers

- `app.include_router(auth.router, prefix="/api")` and `users.router` under
  `/api`, next to the existing contacts router.

**FastAPI note**: middleware wraps every request/response; exception handlers
turn a raised `RateLimitExceeded` into your custom 429 body instead of a stack
trace.

---

## Phase 10 — Protect & scope the contacts API

### [ ] 10.1 Thread `current_user` through the contacts layers

- `ContactRepository`: every method filters/sets by `user_id`
  (`get_by_id(id, user_id)`, `list(user_id, ...)`, `search(user_id, ...)`,
  `birthdays_in_window(user_id, ...)`, `add(data, user_id)`, etc.).
- `ContactService`: methods take `user_id` (or the `User`) and pass it down;
  "not found OR not owned" → `ContactNotFound`.

### [ ] 10.2 Add auth to the contacts router (`src/api/contacts.py`)

- Add `current_user: User = Depends(get_current_user)` to all six handlers;
  pass `current_user.id` into the service. Set `user_id` from `current_user` on
  create. Keep the `/birthdays` before `/{contact_id}` ordering.

**FastAPI note**: adding one `Depends(get_current_user)` parameter is all it
takes to make a route require a valid token — no decorator, no manual header
parsing.

---

## Phase 11 — Tests

### [ ] 11.1 Update fixtures (`tests/conftest.py`)

- Add `test_user` (confirmed) and `auth_headers`. Make the contacts tests send
  `auth_headers`.
- Stub the email background task (no SMTP) and the Cloudinary upload (fixed
  URL) via `app.dependency_overrides` / monkeypatch.

### [ ] 11.2 `tests/test_auth.py`

- Register → 201 + body; duplicate email → 409; stored password ≠ raw (hashed);
  login → access+refresh pair (refresh persisted); wrong password → 401;
  unconfirmed login → 401; confirm flips the flag; bad token → 422;
  `refresh_token` → new pair; refresh token used as bearer → 401 (`token_type`);
  rotated/stale refresh token → 401.

### [ ] 11.3 `tests/test_users.py`

- `/me` returns the user; no token → 401; over-limit → 429; `/avatar` updates
  the URL (Cloudinary stubbed).

### [ ] 11.4 `tests/test_contacts_ownership.py` + update existing contacts tests

- User A can't touch user B's contact (404); list returns only the caller's
  contacts. Update `test_contacts_*` to authenticate.

### [ ] 11.5 Full run

- `uv run pytest` green. Confirm repo/service/api for both `users` and
  `contacts` are exercised.

---

## Phase 12 — Docker & docs

### [ ] 12.1 Pass new env to the `api` service

- Extend `docker-compose.yml` `environment:` (or add `env_file: .env`) with the
  JWT/mail/cloudinary/CORS vars. Migrations still run as the one-shot
  `docker compose run --rm api uv run alembic upgrade head`.

### [ ] 12.2 End-to-end via full Docker

- `docker compose down -v` → `up -d --build` → migrate → register/confirm/login
  → call protected contacts endpoints with the token → hit `/me` 11× to see
  429 → upload an avatar.

### [ ] 12.3 Update `README.md`

- New endpoints table (auth + users), the auth flow, every new env var, the
  rate-limit note, and the link to `/docs`.

---

## Phase 13 — Submission

### [ ] 13.1 Final cleanup

- No stray prints / TODOs; `.env` not committed; `uv run pytest` green;
  `docker compose up --build` green; `pre-commit run --all-files` clean.

### [ ] 13.2 Tag and zip

- Tag the final commit; push.
- Zip the working tree as `ДЗ11_ПІБ.zip`; upload to LMS with the repo URL.
  *(LMS deadline shown 23:45, 1 Jun — confirm late-submission rules.)*

---

## Step count: ~36. Estimated review surface per step: 30–150 lines of diff.
