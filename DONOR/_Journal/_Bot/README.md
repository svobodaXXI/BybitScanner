# Trading Journal

Trading Journal is a private trading-journal platform focused on reliable trade history, automatic exchange data, configurable statistics, and a responsive web interface. The Website is the primary application; Telegram is a companion for notifications, Attention workflows, quick updates, and compact KPI summaries.

## Source of truth

The repository is the authoritative project source. Before starting substantial work, read:

- `TRADING_JOURNAL_PROJECT_MASTER.md` — current architecture, product decisions, completed phases, handoff state, and next work.
- `TRADING_JOURNAL_PROJECT_PLAN_V2_0_DYNAMIC_STATS_AUTO.md` — detailed implementation plan for dynamic statistics and automatic data.
- `README_SETUP.md` — local PostgreSQL and environment setup.
- `README_MINIAPP.md` — current FastAPI Mini App / web frontend base.
- `README_BYBIT_ADAPTER.md` and `README_BYBIT_IMPORT.md` — Bybit integration and historical import.

## Architecture

```text
app/
├── core/             # domain entities and rules
├── application/      # use cases, ports, DTOs, statistics/attention orchestration
├── infrastructure/   # SQLAlchemy, PostgreSQL, repositories, exchange adapters
├── miniapp/          # FastAPI API and current web frontend base
└── telegram/         # Telegram companion interface

test/
├── application/
├── config/
├── core/
├── dev_harness/
├── infrastructure/
├── integration/
├── miniapp/
└── telegram/

alembic/
└── versions/
```

## Current stack

- Python 3.12
- FastAPI
- aiogram
- SQLAlchemy 2.x
- asyncpg
- Alembic
- PostgreSQL 16
- pytest
- Docker / Docker Compose
- Bybit integration

## Local setup

Create a virtual environment, install dependencies, and configure `.env` from `.env.example`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For the local PostgreSQL bootstrap and required environment variables, follow `README_SETUP.md`.

## Database migrations

Runtime and test databases are intentionally separate. Never point integration tests at the production/runtime database.

```powershell
alembic upgrade head
```

The current migration chain is documented in `TRADING_JOURNAL_PROJECT_MASTER.md`.

## Tests

Run the full regression suite before merging substantial changes:

```powershell
pytest
```

PostgreSQL integration tests require `TEST_DATABASE_URL`. The CI workflow provisions PostgreSQL 16, creates a separate test database, applies Alembic migrations, and runs the full suite.

## Development workflow

Substantial work should follow:

```text
Issue
  ↓
feature/fix/chore branch
  ↓
implementation
  ↓
pytest
  ↓
Pull Request
  ↓
review + CI
  ↓
merge to main
```

Avoid unrelated changes in the same commit or PR.

## Security

Never commit secrets. In particular, keep `.env`, exchange API secrets, Telegram bot tokens, database passwords, OpenAI keys, and runtime logs out of version control. Frontend code must not contain trusted authorization logic or secrets; authentication, authorization, and tenant/account isolation belong on the server.
