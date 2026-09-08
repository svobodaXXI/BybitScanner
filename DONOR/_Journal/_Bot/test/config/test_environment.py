import pytest
from pathlib import Path

from app.infrastructure.persistence.database import (
    get_database_url,
    get_test_database_url,
    mask_database_url,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_test_database_url_never_falls_back_to_runtime_database(monkeypatch):
    monkeypatch.setattr("app.infrastructure.persistence.database.load_environment", lambda: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://user:password@localhost/test")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        get_database_url()
    assert get_test_database_url().endswith("/test")


def test_mask_database_url_hides_password_and_preserves_safe_target():
    masked = mask_database_url("postgresql+asyncpg://trading_journal:secret@127.0.0.1:5432/trading_journal")
    assert masked == "postgresql+asyncpg://trading_journal:%2A%2A%2A@127.0.0.1:5432/trading_journal"
    assert "secret" not in masked


def test_empty_database_url_mask_is_safe():
    assert mask_database_url("") == "<not configured>"


def test_compose_and_env_example_define_separate_local_databases():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "image: postgres:16" in compose
    assert "trading_journal_pgdata" in compose
    assert "pg_isready" in compose
    assert "POSTGRES_TEST_DB" in compose
    assert "DATABASE_URL=" in env_example
    assert "TEST_DATABASE_URL=" in env_example
