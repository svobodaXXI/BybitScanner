#!/usr/bin/env bash
set -eu

test_database="${POSTGRES_TEST_DB:-trading_journal_test}"

case "$test_database" in
  (""|*[!a-zA-Z0-9_]*|[0-9]*)
    echo "POSTGRES_TEST_DB must be a simple PostgreSQL database name" >&2
    exit 1
    ;;
esac

if ! psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --tuples-only --no-align \
  --command "SELECT 1 FROM pg_database WHERE datname = '$test_database'" | grep -q 1; then
  psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --command "CREATE DATABASE \"$test_database\""
fi
