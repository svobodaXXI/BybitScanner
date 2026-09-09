from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from terminal.diary import DiaryDecisionStore, SetupInstanceId, SetupInstanceRecord
from terminal.domain.models import Origin, PositionSide, Symbol
from terminal.runtime.paper_http_server import PaperHttpHandler


def test_diary_setups_get_route_reads_d2_store(tmp_path: Path):
    diary_path = tmp_path / "paper_runtime.trading_diary.sqlite3"
    with DiaryDecisionStore.open(diary_path) as store:
        store.create_setup_instance(
            SetupInstanceRecord(
                setup_instance_id=SetupInstanceId("setup-http-1"),
                symbol=Symbol("BTCUSDT"),
                timeframe="1m",
                pattern="Falling Wedge",
                direction=PositionSide.LONG,
                strategy_version="strategy-v1",
                setup_id="falling-wedge",
                hypothesis_id=None,
                entry_mode="breakout_retest",
                origin=Origin.ROBOT,
                created_at_ms=100,
            )
        )

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.diary_setup_store_path = diary_path
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urlopen(f"http://{host}:{port}/api/diary/setups", timeout=2) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["ok"] is True
        assert payload["source"] == "TRADING_DIARY_D2"
        assert len(payload["setups"]) == 1
        setup = payload["setups"][0]
        assert setup["setup_instance_id"] == "setup-http-1"
        assert setup["status"] == "ADMITTED"
        assert setup["needs_attention"] is True
        assert setup["missing_evidence"] == ["MISSING_DECISION_EVENTS"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
