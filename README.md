# Python App
 
A FastAPI backend with JWT authentication, an admin role, and a PostgreSQL
database (SQLModel + Alembic), run with Docker Compose. It started as a
walk-through of the FastAPI tutorial; the users, items, tags and auth parts are
now real, database-backed features. The rest are still tutorial examples.
 
## Stack
 
| Area | Technology |
| --- | --- |
| Language | Python 3.15 (`requires-python = ">=3.15"`, image `python:3.15-slim`) |
| Web framework | FastAPI (`fastapi[standard]`), Uvicorn via the FastAPI CLI |
| Database | PostgreSQL 16 with the `psycopg` (v3) driver |
| ORM / models | SQLModel (SQLAlchemy + Pydantic) |
| Migrations | Alembic |
| Auth | OAuth2 password flow, PyJWT access tokens, rotating refresh tokens, `pwdlib` (Argon2) password hashing |
| Rate limiting | slowapi |
| Settings | pydantic-settings, python-dotenv |
| Packaging | uv (`pyproject.toml`, `uv.lock`) |
| Containers | Docker, Docker Compose |
| Tooling | pytest, ruff (dev dependencies) |
| Other | Jinja2 templates, WebSockets, httpx, email-validator |
 
## Quick start
 
```bash
# 1. Secret key for signing JWTs (read by compose from the root .env)
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
 
# 2. Build and start the app and the database
docker compose up --build
 
# 3. Open the interactive API docs
#    http://localhost:8000/docs
```
 
On every start, the app container first runs `alembic upgrade head`, so the
database schema is created and kept up to date automatically in development.
 
Create the first admin by promoting a registered user (see
[Admin role](#admin-role)).
 
## Project layout
 
```
python_app/
├── src/my_first_app/
│   ├── main.py            # creates the app: middleware, exception handlers, routers
│   ├── config.py          # app settings (reads src/my_first_app/.env)
│   ├── database.py        # engine, session dependency, constraint naming convention
│   ├── models.py          # all tables and request/response schemas
│   ├── ratelimit.py       # shared slowapi limiter
│   ├── cleanup.py         # deletes expired refresh tokens (run on a schedule)
│   ├── dependencies.py    # legacy tutorial dependencies (static tokens)
│   ├── exceptions.py      # custom exception handlers
│   ├── internal/admin.py  # tutorial admin router (protected by admin role)
│   ├── routers/           # auth, users, items, heroes, streaming, ...
│   ├── static/
│   └── templates/
├── migrations/            # Alembic environment and versions
├── alembic.ini
├── tests/
├── compose.yaml           # development setup: app + Postgres
├── Dockerfile
├── .dockerignore
├── pyproject.toml / uv.lock / .python-version
└── .env                   # SECRET_KEY for compose (git-ignored)
```
 
- `main.py` registers middleware, exception handlers and routers. The session
  dependency (`get_session`) and the legacy token dependency (`verify_token`,
  an alias of `get_token_header`) stay importable from `my_first_app.main` for
  test overrides.
- Some features expose several router objects so route registration order is
  preserved (`items.router`, `items.tags_router`, `items.demo_router`,
  `users.router`, `users.admin_router`).
- There is no `create_all` at startup anymore. Alembic owns the schema.
## API overview
 
Interactive docs: `http://localhost:8000/docs` (use **Authorize** to log in).
 
**Authentication** (`routers/auth.py`)
 
| Route | Description |
| --- | --- |
| `POST /auth/register` | Create a user (rate limited: 10/hour per IP) |
| `POST /token` | Log in with form fields `username` and `password`; returns an access token and a refresh token (10/minute per IP) |
| `POST /auth/refresh` | Exchange a refresh token for a new pair (30/minute per IP) |
| `POST /auth/logout` | End this login session (revokes the refresh-token family) |
| `POST /auth/logout-all` | End all sessions of the current user |
 
**Users** (`routers/users.py`, login required)
 
| Route | Description |
| --- | --- |
| `GET /users/` | List users |
| `GET /users/me` | Current user (includes `is_admin`, `disabled`) |
| `GET /users/{username}` | One user |
| `GET /admin/users/` | List users with admin fields (admin only) |
| `PATCH /admin/users/{id}` | Set `is_admin` / `disabled` (admin only; admins can't demote or disable themselves) |
 
**Items and tags** (`routers/items.py`, login required)
 
| Route | Description |
| --- | --- |
| `GET /items/` | List items; optional `?tag=rock`, `offset`, `limit` |
| `POST /items/` | Create an item with optional `tags` and `images` |
| `GET /items/{id}` | One item |
| `PATCH /items/{id}` | Update; `tags` replaces all tags (`[]` clears them) |
| `DELETE /items/{id}` | Delete an item with its images and tag links |
| `POST /items/{id}/images` | Add an image |
| `DELETE /items/{id}/images/{image_id}` | Remove an image |
| `GET /tags/` | List tags |
 
Anyone logged in can read items. Only the owner or an admin can change or
delete them.
 
**Examples, not stored in the database**
 
- Tutorial demos in `items.py` (`demo_router`, login required):
  `/filtered-items/`, `/books/`, `/items-template/{id}`, `/new-items/{item_id}`,
  `/models/{model_name}`, `/images/multiple/`.
- Unchanged tutorial features: heroes, streaming, WebSocket, invoice, form and
  file uploads, and the examples router.
## Authentication
 
- Passwords are hashed with Argon2 (`pwdlib`). Login takes the same time for
  unknown and known usernames.
- **Access token:** JWT, valid 15 minutes, signed with `SECRET_KEY`. The user
  is reloaded from the database on every request, so disabling a user or
  removing admin rights takes effect immediately.
- **Refresh token:** random string, valid 14 days, stored only as a SHA-256
  hash in `refresh_tokens`.
- **Rotation:** each refresh revokes the used token and issues a new one in
  the same family. If an already-used token is presented again, the whole
  family is revoked (assumed theft) and the user must log in again.
- Access tokens can't be revoked individually: after logout, the current one
  works until it expires (at most 15 minutes).
- Rate limits are per client IP and kept in each worker's memory.
### Admin role
 
`users.is_admin` is a boolean flag. There is no endpoint to create the first
admin. Promote a registered user directly in the database:
 
```bash
docker compose exec db psql -U app -d app \
  -c "update users set is_admin = true where username = '<your-username>';"
```
 
## Database setup
 
PostgreSQL 16 runs as the `db` service. Data is stored in the `pgdata` Docker
volume, so it survives restarts.
 
| Setting | Value |
| --- | --- |
| Database / user / password | `app` / `app` / `app` (development only) |
| URL inside the compose network | `postgresql+psycopg://app:app@db:5432/app` |
| Host from other containers | `db` (the service name) |
 
The URL must start with `postgresql+psycopg://` so SQLAlchemy uses the
installed psycopg 3 driver. The app reads it from the `DATABASE_URL`
environment variable, which is required.
 
### Tables
 
| Table | Contents |
| --- | --- |
| `users` | username (unique), email (unique), full name, Argon2 password hash, `disabled`, `is_admin` |
| `items` | name, description, price `NUMERIC(10,2)`, tax, `is_offer`, `owner_id` → users, `created_at`, `updated_at` |
| `tags` | unique lowercase tag names |
| `item_tags` | many-to-many link between items and tags (cascade delete) |
| `item_images` | `item_id` → items (cascade delete), url, name |
| `refresh_tokens` | `user_id` → users (cascade delete), token hash, `family_id`, `expires_at`, `revoked_at` |
| `hero` | example table from the heroes tutorial |
| `alembic_version` | current migration (managed by Alembic) |
 
### Connect with a database tool
 
The database port is not published by default. To use DBeaver, pgAdmin or
VS Code, add this under the `db` service in `compose.yaml`:
 
```yaml
    ports:
      - "127.0.0.1:5432:5432"   # reachable from this machine only
```
 
Then run `docker compose up -d` and connect to host `localhost`, port `5432`,
database `app`, user `app`, password `app`. Use `5433:5432` instead if your
machine already runs its own Postgres. For a quick look without a port:
 
```bash
docker compose exec db psql -U app -d app
```
 
### Migrations (Alembic)
 
The workflow after changing a model in `models.py`:
 
```bash
# 1. Generate a migration (--user keeps the new file owned by you, not root)
docker compose exec --user "$(id -u):$(id -g)" app alembic revision --autogenerate -m "describe change"
 
# 2. Open the new file in migrations/versions/ and review it
 
# 3. Apply it (the compose command also runs this on every start)
docker compose exec app alembic upgrade head
```
 
Other useful commands:
 
```bash
docker compose exec app alembic current        # which migration is applied
docker compose exec app alembic history        # all migrations
docker compose exec app alembic downgrade -1   # undo the last migration
```
 
Notes:
 
- Autogenerate can't detect renames (it sees a drop plus an add, which loses
  data). Edit such migrations by hand.
- Adding a NOT NULL column to a table with rows needs a `server_default`.
- Every module that defines a `table=True` model must be imported in
  `migrations/env.py`, or autogenerate won't see it.
- Constraint names follow the naming convention in `database.py`.
### Reset and maintenance
 
```bash
docker compose down -v    # deletes the pgdata volume: all data is lost
docker compose exec app python -m my_first_app.cleanup   # delete expired refresh tokens
```
 
Schedule the cleanup daily, for example with cron on the host:
 
```
0 3 * * * cd ~/python_app && docker compose exec -T app python -m my_first_app.cleanup
```
 
## Configuration
 
| Variable | Set in | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `compose.yaml` | Database connection URL (required) |
| `SECRET_KEY` | root `.env`, passed through `compose.yaml` | JWT signing key (required). Generate with `openssl rand -hex 32` |
| `UV_NO_DEV` | `Dockerfile` (`1`), `compose.yaml` (`0`) | Install dev dependencies (pytest, ruff) in development only |
| `ADMIN_EMAIL`, `APP_NAME` | `src/my_first_app/.env` | Application settings loaded by `config.py` |
 
`.env` files are listed in `.dockerignore`, so they are never copied into the
image. A production container must receive all variables from its environment.
Never commit `.env`.
 
## Docker
 
### How the setup works
 
**`Dockerfile`**
 
- Builds from `python:3.15-slim` and copies the `uv` binary from its official
  image.
- Installs dependencies in two steps: first only from `pyproject.toml` and
  `uv.lock`, then the project source. Code changes don't reinstall
  dependencies, so rebuilds stay fast. A cache mount speeds up repeated
  installs.
- `uv sync --locked` fails the build if `uv.lock` doesn't match
  `pyproject.toml`.
- Puts `/app/.venv/bin` on `PATH`, so commands like `alembic` and `fastapi`
  run directly, without `uv run`.
- Copies `alembic.ini` and `migrations/` so the image can migrate its own
  database.
- Default command: `fastapi run` (production mode, no auto-reload).
**`compose.yaml`** (development)
 
- `app`: built from the `Dockerfile`, but overrides the command with
  `alembic upgrade head && fastapi dev ...` so migrations run first and code
  changes reload automatically.
- `volumes: .:/app` mounts your project folder into the container, so edits
  show up immediately. `/app/.venv` is an anonymous volume that keeps the
  container's virtual environment from being replaced by your local one.
- `UV_NO_DEV: "0"` installs dev dependencies in this container.
- `db`: Postgres with a healthcheck (`pg_isready`). The app waits until the
  database reports healthy before it starts.
- Port `8000` is published for the API. The database port is not published
  unless you add it.
### Commands
 
| Command | What it does |
| --- | --- |
| `docker compose up --build` | Build images and start everything in the foreground |
| `docker compose up -d` | Start in the background |
| `docker compose up --build -V` | Rebuild and recreate the `.venv` volume. Use this after changing dependencies |
| `docker compose ps` | Show running services and ports |
| `docker compose logs -f app` | Follow the app logs |
| `docker compose restart app` | Restart the app (also re-runs migrations) |
| `docker compose down` | Stop and remove containers (data is kept) |
| `docker compose down -v` | Same, and delete the database volume |
| `docker compose exec app sh` | Open a shell in the running app container |
| `docker compose exec db psql -U app -d app` | Open a Postgres shell |
| `docker compose exec app uv run pytest` | Run the tests |
| `docker compose exec app uv run ruff check .` | Lint the code |
| `docker compose exec app uv run ruff format .` | Format the code |
 
`exec` runs a command in a container that is already running. Add
`--user "$(id -u):$(id -g)"` when a command creates files in the project
folder (for example `alembic revision`), so they aren't owned by root.
 
Tests run against the same database as development. Be careful with tests that
write data.
 
### Dependencies
 
```bash
uv add <package>          # add a dependency (updates pyproject.toml and uv.lock)
uv add --dev <package>    # add a dev dependency
uv lock                   # refresh uv.lock after editing pyproject.toml by hand
docker compose up --build -V
```
 
Commit `pyproject.toml` and `uv.lock` together. A build error saying the
lockfile needs to be updated means you forgot `uv lock`.
 
### Production image
 
```bash
docker build -t my-first-app .
 
# apply migrations as a separate step before starting new containers
docker run --rm \
  -e DATABASE_URL=... -e SECRET_KEY=... \
  my-first-app alembic upgrade head
 
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=... -e SECRET_KEY=... \
  -e ADMIN_EMAIL=... -e APP_NAME=... \
  my-first-app
```
 
Before deploying:
 
- Use real database credentials and a new `SECRET_KEY`. The `app`/`app` login
  is for development only.
- Serve over HTTPS and restrict CORS origins.
- Behind a reverse proxy, start the app with `--proxy-headers`, or rate limits
  will see every request as coming from the proxy.
- With several workers or containers, give the limiter a shared store (for
  example Redis through `storage_uri`), because counters are per process.
- Run migrations once per deploy, not in every container.
## Run without Docker
 
You need a reachable PostgreSQL (publish the port as shown above) and these
variables exported:
 
```bash
export DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app
export SECRET_KEY=$(openssl rand -hex 32)
uv run alembic upgrade head
uv run fastapi dev
```
 
The FastAPI entrypoint is `my_first_app.main:app` (set in `pyproject.toml`).
In VS Code, select the project's `.venv` as the Python interpreter and use the
**FastAPI: debug** launch configuration.
 
## Troubleshooting
 
| Symptom | Fix |
| --- | --- |
| Build fails: lockfile needs to be updated | Run `uv lock` and rebuild |
| New dependency not found in the container | `docker compose up --build -V` |
| `SECRET_KEY` error on `docker compose up` | Create the root `.env` (see Quick start) |
| Can't connect to the database from a tool | Publish the port (see Database setup) |
| Port 5432 already in use | Map another host port, e.g. `127.0.0.1:5433:5432` |
| Migration files owned by root | `sudo chown -R $USER:$USER migrations`, and use `--user` next time |
| Autogenerated migration is empty | The model isn't imported in `migrations/env.py`, or nothing changed |
| `429 Too Many Requests` in tests | Disable the limiter in test setup: `limiter.enabled = False` |
 
## Known route conflicts
 
These tutorial examples are preserved as-is. Resolving them would change the
API:
 
| Routes | Current behavior and possible follow-up |
| --- | --- |
| `GET /` | The JSON greeting wins; OpenAPI describes the later upload form. Give the form a distinct path or choose one root. |
| `POST /uploadfile/` | The multiple-file handler wins; OpenAPI describes the later handler with different fields. Give them distinct paths or agree on one contract. |
| `/items/stream`, `/items/stream-retry` | `GET /items/{item_id}` is registered first and takes these paths, so they return `422` (the id must be an integer). Include the streaming router before the items router, or move the streaming examples to another prefix. |
 
Resolved: the duplicate `POST /token` and `GET /users/` examples and the
overlapping demo item routes no longer exist. The tutorial's fake auth
helpers, fake user store and static-token checks were replaced by the database
and JWT flow above.