"""Read-only geometry companion of the existing PAPER Robot monitor.

One bounded in-process worker, not a standalone service or market subscription.
A candidate without retained native seed coverage stays unobserved. All journal
IO and geometry computation happen outside the socket and trading owner.
"""
from __future__ import annotations

from contextlib import closing
import logging
from pathlib import Path
import sqlite3
import threading
import time

from .wedge_control_anchor import attach_control_anchor_observation, load_control_anchor_seed

LOGGER = logging.getLogger(__name__)
MAX_TRACKS = 8
SYNC_SECONDS = 0.5
POLL_SECONDS = 0.02


def _ready_records(path, candidate_id=None):
    from terminal.domain.models import TradingAccountId
    from terminal.persistence.sqlite_store import SQLiteStore

    path = Path(path)
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True,
                                 timeout=0.2, isolation_level=None)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        store = SQLiteStore(conn, path, 200)
        account = TradingAccountId("paper")
        state = store.get_robot_runtime_state(account)
        if state is None or state.mode != "ROBOT_RUNNING" or state.recovery_status != "READY":
            return None, ()
        records = (store.load_robot_candidates_by_status(account, ("APPROVED", "OPEN"))
                   if candidate_id is None else (store.get_robot_candidate(candidate_id),))
        return state.version, tuple(r for r in records if r is not None
                                    and r.trading_account_id == account
                                    and r.status in ("APPROVED", "OPEN")
                                    and r.signal_snapshot.get("pattern")
                                    in ("Falling Wedge", "Rising Wedge"))


class WedgeRuntimeObserver:
    def __init__(self, hub, database_path, *, read_records=None, load_seed=None):
        self.hub = hub
        self.path = Path(database_path)
        self.read_records = read_records or (lambda candidate_id=None: _ready_records(self.path, candidate_id))
        self.load_seed = load_seed or load_control_anchor_seed
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="robot-wedge-geometry", daemon=True)
        self.tracks = {}
        self.epoch = None
        self.seeds = {}

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)

    def _drop(self, candidate_id):
        track, _, _ = self.tracks.pop(candidate_id)
        track.source.detach_print_inbox(track.inbox)

    def _clear(self):
        for candidate_id in tuple(self.tracks):
            self._drop(candidate_id)
        self.seeds.clear()

    def _sources(self):
        return {c.impulse_observation.symbol: c.impulse_observation
                for c in self.hub.list_flow_contexts()
                if getattr(c, "impulse_observation", None) is not None}

    def _allowed(self, candidate_id, identity, source, epoch):
        if self.stop.is_set() or self._sources().get(source.symbol) is not source:
            return False
        try:
            ready, records = self.read_records(candidate_id)
            return (ready == epoch and len(records) == 1
                    and records[0].candidate_id == candidate_id
                    and records[0].snapshot_sha256 == identity
                    and records[0].symbol.value == source.symbol)
        except Exception:
            return False

    def sync(self):
        """Reconcile only existing contexts and exact active candidate identities."""
        epoch, records = self.read_records()
        if epoch != self.epoch or epoch is None or self.stop.is_set():
            self._clear()
            self.epoch = epoch
        if epoch is None or self.stop.is_set():
            return
        sources = self._sources()
        active = {r.candidate_id: r for r in records}
        counts = {}
        for r in records:
            counts[r.symbol.value] = counts.get(r.symbol.value, 0)+1
        for key, (track, identity, _) in tuple(self.tracks.items()):
            r = active.get(key)
            if (r is None or r.snapshot_sha256 != identity or not track.valid
                    or counts.get(track.source.symbol) != 1
                    or sources.get(track.source.symbol) is not track.source):
                self._drop(key)
        for key in tuple(self.seeds):
            if key not in active:
                self.seeds.pop(key)
        for key, r in active.items():
            if len(self.tracks) >= MAX_TRACKS:
                break
            source = sources.get(r.symbol.value)
            if key in self.tracks or source is None or counts[r.symbol.value] != 1:
                continue
            cached = self.seeds.get(key)
            if cached is None or cached[0] != r.snapshot_sha256:
                seed = self.load_seed(r)
                if seed is None:
                    continue  # source archive may not have been published yet
                self.seeds[key] = (r.snapshot_sha256, seed)
            else:
                seed = cached[1]
            track = attach_control_anchor_observation(seed, source, journal_database_path=self.path)
            if track is not None:
                identity = r.snapshot_sha256
                track.allow_publish = lambda key=key, identity=identity, source=source, epoch=epoch: self._allowed(key, identity, source, epoch)
                self.tracks[key] = (track, identity, epoch)

    def drain(self):
        for key, (track, _, _) in tuple(self.tracks.items()):
            if self.stop.is_set():
                break
            for proposal in track.consume():
                if proposal.get("revision_outcome") in ("RECORDED", "JOURNAL_BLOCKED", "REBUILD_UNAVAILABLE"):
                    LOGGER.info("WEDGE_GEOMETRY %s candidate=%s trade=%s",
                                proposal["revision_outcome"], key, proposal.get("source_trade_id"))
            if not track.valid:
                self._drop(key)

    def _run(self):
        next_sync = 0.
        try:
            while not self.stop.is_set():
                try:
                    now = time.monotonic()
                    if now >= next_sync:
                        self.sync()
                        next_sync = now+SYNC_SECONDS
                    self.drain()
                except Exception as error:
                    self._clear()
                    next_sync = time.monotonic()+SYNC_SECONDS
                    LOGGER.warning("Wedge geometry observation unavailable: %s", type(error).__name__)
                self.stop.wait(POLL_SECONDS)
        finally:
            self._clear()
