from pathlib import Path

from terminal.diary.decision_models import SetupInstanceId, SetupInstanceRecord
from terminal.diary.decision_store import DiaryDecisionStore
from terminal.diary.setup_runtime import decision_store_path, project_setup_store
from terminal.domain.models import Origin, PositionSide, Symbol


def test_decision_store_path_is_separate_from_runtime_database(tmp_path: Path):
    runtime_path = tmp_path / "paper_runtime.sqlite3"
    assert decision_store_path(runtime_path) == tmp_path / "paper_runtime.trading_diary.sqlite3"


def test_project_setup_store_reads_d2_evidence_without_fabricating_records(tmp_path: Path):
    path = tmp_path / "paper_runtime.trading_diary.sqlite3"
    with DiaryDecisionStore.open(path) as store:
        store.create_setup_instance(
            SetupInstanceRecord(
                setup_instance_id=SetupInstanceId("setup-1"),
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

    projection = project_setup_store(path)

    assert projection["source"] == "TRADING_DIARY_D2"
    assert len(projection["setups"]) == 1
    setup = projection["setups"][0]
    assert setup["setup_instance_id"] == "setup-1"
    assert setup["status"] == "ADMITTED"
    assert setup["decision_state"] is None
    assert setup["needs_attention"] is True
    assert setup["missing_evidence"] == ["MISSING_DECISION_EVENTS"]


def test_project_setup_store_initializes_empty_observational_store(tmp_path: Path):
    path = tmp_path / "missing.trading_diary.sqlite3"
    projection = project_setup_store(path)

    assert projection == {"setups": [], "source": "TRADING_DIARY_D2"}
    assert path.exists()
