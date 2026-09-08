# Trading Journal — local and server bootstrap

The project uses one configuration mechanism: `python-dotenv` loads `.env` without overriding variables explicitly exported by the shell. Runtime, Mini App, Telegram, Bybit, and Alembic read the same environment boundary.

## Windows PowerShell

From a fresh checkout:

```powershell
cd D:\Trading\_Journal\_Bot
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env: set DATABASE_URL, TEST_DATABASE_URL, TELEGRAM_BOT_TOKEN,
# TELEGRAM_ALLOWED_USER_ID and JOURNAL_ACCOUNT_ID.
docker compose up -d postgres
docker compose ps
docker compose logs postgres
alembic upgrade head
alembic current
alembic heads
uvicorn app.miniapp.server:create_app --factory --host 127.0.0.1 --port 8000
```

In another activated PowerShell window, start the Telegram Bot without network polling tests:

```powershell
cd D:\Trading\_Journal\_Bot
.\.venv\Scripts\Activate.ps1
python -m app.telegram.bot
```

The Mini App root is `http://127.0.0.1:8000/`. API endpoints still require valid Telegram WebApp `initData`.

## Linux/server bootstrap

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env with server credentials and URLs.
docker compose up -d postgres
docker compose ps
docker compose logs postgres
alembic upgrade head
alembic current
alembic heads
uvicorn app.miniapp.server:create_app --factory --host 0.0.0.0 --port 8000
```

Run the Bot separately with `python -m app.telegram.bot`. A reverse proxy/TLS and a process supervisor are intentionally outside this bootstrap phase.

## Database policy

Compose uses PostgreSQL 16, a named volume, and the `POSTGRES_*` variables. The first initialization creates both `POSTGRES_DB` (runtime) and `POSTGRES_TEST_DB` (integration tests) through `docker/postgres/initdb/01-create-test-database.sh`. Initialization scripts run only when the named volume is first created; changing the test DB name later requires an explicit DBA/bootstrap action.

`DATABASE_URL` is for the runtime database. `TEST_DATABASE_URL` is independent and tests never fall back to `DATABASE_URL`. If `TEST_DATABASE_URL` is missing, PostgreSQL integration tests skip with a clear reason.

Normal stop/start preserves data:

```text
docker compose stop
docker compose start
```

`docker compose down -v` deletes the local named volume and is destructive. Use it only when intentionally recreating a disposable development database; never use it as part of normal startup or against production.

For a fresh disposable-dev acceptance, explicitly confirm the target is local/dev, run `docker compose down -v`, then `docker compose up -d postgres`, `alembic upgrade head`, `alembic current`, and `alembic heads`. Expected head: `0002_instruments`.

## Smoke checklist

```text
docker compose ps
docker compose exec postgres pg_isready -U trading_journal -d trading_journal
alembic current
alembic heads
python -c "from app.miniapp.server import create_app; create_app(); print('miniapp-composition-ok')"
pytest test/telegram -q
```

These checks do not call Telegram or Bybit. Do not place Bybit secrets in smoke commands.

## Backup and restore

Create a plain SQL backup from the runtime database (the command runs `pg_dump` inside the container):

```text
docker compose exec -T postgres pg_dump -U trading_journal -d trading_journal > trading_journal_backup.sql
```

Restore into a clean, already-created runtime database after verifying the target and backup file:

```text
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U trading_journal -d trading_journal < trading_journal_backup.sql
```

For a separate clean restore database, create it explicitly with PostgreSQL administration tools, run `alembic upgrade head` as appropriate, and restore only after checking the destination. No production restore automation is included.

## Port conflicts

If host port 5432 is busy, set `POSTGRES_PORT=55432` in `.env` and use the same port in both `DATABASE_URL` and `TEST_DATABASE_URL`; do not kill the process automatically. If port 8000 is busy, start Uvicorn on another explicit port such as `--port 8001`.

## Configuration safety

`.env` and other `.env.*` files are ignored; `.env.example` remains tracked. Never commit API keys, database passwords, dumps, or backups. Database URLs are environment-driven and can be masked for diagnostics with the application `mask_database_url` helper; passwords are never included in safe output.
