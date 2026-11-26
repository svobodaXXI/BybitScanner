import json
import pytest
from research.local_replay_viewer.paper_episode_local_store import (
    release_archive_root, recover_release_episode, store_episode, LocalEpisodeConflict,
)

def test_release_episode_continuity(tmp_path):
    root = tmp_path / "MachineTime"
    def release(sha):
        app = root / "releases" / sha / "MachineTime"
        app.mkdir(parents=True)
        (app / "desktop-build-sha.txt").write_text(sha, encoding="ascii")
        return app
    old, new = release("a"*40), release("b"*40)
    episode = "te_" + "c"*24
    doc = dict(ok=True, trade_episode_id=episode,
               schema="BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
               namespace="PAPER_READ_ONLY", account_id="paper",
               source="PAPER_EXECUTIONS_ATTRIBUTED",
               replay_evidence="EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
               owner="ROBOT", execution_allocations=[{"qty":"1"}])
    raw = json.dumps(doc).encode()
    store_episode(old / "paper-episode-facts", raw)
    assert release_archive_root(old) == release_archive_root(new)
    assert recover_release_episode(new, episode) == raw
    assert (old / "paper-episode-facts" / (episode+".json")).read_bytes() == raw
    doc["execution_allocations"] = [{"qty":"2"}]
    store_episode(new / "paper-episode-facts", json.dumps(doc).encode())
    with pytest.raises(LocalEpisodeConflict):
        recover_release_episode(new, episode)
