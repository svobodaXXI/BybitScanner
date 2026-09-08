import sys

import pytest

from app.application import HistoricalExecutionBackfillSummary
from app.infrastructure.exchanges.bybit import historical_import
from app.infrastructure.exchanges.bybit.historical_import import render_import_summary


def test_render_import_summary_prints_sanitized_error_details_and_returns_failure(capsys):
    summary = HistoricalExecutionBackfillSummary(
        fetched=2,
        processed=1,
        already_processed=0,
        trades_created=1,
        trades_updated=0,
        trades_closed=0,
        errors=1,
        error_messages=("exec-42: IntegrityError: FK failed",),
    )

    exit_code = render_import_summary(summary)

    output = capsys.readouterr().out
    assert "BYBIT_HISTORICAL_IMPORT" in output
    assert "errors=1" in output
    assert "ERROR exec-42: IntegrityError: FK failed" in output
    assert exit_code == 1


def test_render_import_summary_returns_success_without_error_lines(capsys):
    summary = HistoricalExecutionBackfillSummary(
        fetched=1,
        processed=1,
        already_processed=0,
        trades_created=1,
        trades_updated=0,
        trades_closed=0,
        errors=0,
    )

    exit_code = render_import_summary(summary)

    output = capsys.readouterr().out
    assert "errors=0" in output
    assert "ERROR " not in output
    assert exit_code == 0


def test_main_propagates_import_failure_as_process_exit(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["historical_import", "--start", "2026-09-05T00:00:00Z"])

    def fake_run(coroutine):
        coroutine.close()
        return 1

    monkeypatch.setattr(historical_import.asyncio, "run", fake_run)

    with pytest.raises(SystemExit) as raised:
        historical_import.main()

    assert raised.value.code == 1
