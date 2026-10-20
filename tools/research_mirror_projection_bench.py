"""Benchmark of ``mirror_retest_projection.project_observations`` on scaled copies of the 60 real INTEGRATION-5 records.

Synthetic scaling only multiplies the saved fixture (unique ``observation_id`` per copy, otherwise the same bytes), so
every line stays a valid OBSERVE_ONLY record. Run from the root of the checkout to measure; journals go to ``--work``
(outside the repository). CPU/wall: min of ``--repeat`` runs without tracemalloc; memory: one separate traced run.

    python tools/research_mirror_projection_bench.py --work DIR --out result.json [--label before|after]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

import mirror_retest_projection as projection_module  # noqa: E402
from mirror_retest_projection import project_observations  # noqa: E402

FIXTURE = Path.cwd() / "tests" / "fixtures" / "mirror_integration_5" / "journal_B.jsonl"
SIZES = (60, 600, 3000, 11000)


def build(work: Path, size: int) -> Path:
    path = work / f"journal_{size}.jsonl"
    if path.exists():
        return path
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    with path.open("w", encoding="utf-8") as handle:
        for n in range(size):
            row = dict(rows[n % len(rows)])
            row["observation_id"] = f"{row['observation_id']}-{n // len(rows)}"
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def timed(call, repeat: int):
    best_cpu = best_wall = None
    result = None
    for _ in range(repeat):
        cpu, wall = time.process_time(), time.perf_counter()
        result = call()
        cpu, wall = time.process_time() - cpu, time.perf_counter() - wall
        best_cpu = cpu if best_cpu is None else min(best_cpu, cpu)
        best_wall = wall if best_wall is None else min(best_wall, wall)
    return result, round(best_cpu * 1000, 2), round(best_wall * 1000, 2)


def peak_mb(call) -> float:
    tracemalloc.start()
    call()
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return round(peak / 1e6, 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--polls", type=int, default=20)
    args = parser.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    out = {"label": args.label, "module": str(Path(projection_module.__file__).resolve().name), "sizes": []}
    for size in SIZES:
        path = build(work, size)
        first, cpu0, wall0 = timed(lambda: project_observations(path, after=0, limit=100), args.repeat)
        end = first["total_lines"]
        _, cpu_end, wall_end = timed(lambda: project_observations(path, after=end, limit=100), args.repeat)
        # repeated polling without new records, as a UI would do (stateless caller: same after/journal_id each time)
        cpu, wall = time.process_time(), time.perf_counter()
        for _ in range(args.polls):
            project_observations(path, after=end, limit=100, journal_id=first["journal_id"])
        poll_cpu = round((time.process_time() - cpu) * 1000 / args.polls, 2)
        poll_wall = round((time.perf_counter() - wall) * 1000 / args.polls, 2)
        out["sizes"].append({
            "records": size, "bytes": path.stat().st_size,
            "after_0_limit_100": {"cpu_ms": cpu0, "wall_ms": wall0,
                                  "peak_mb": peak_mb(lambda: project_observations(path, after=0, limit=100))},
            "after_end": {"cpu_ms": cpu_end, "wall_ms": wall_end,
                          "peak_mb": peak_mb(lambda: project_observations(path, after=end, limit=100))},
            "poll_no_new_avg": {"cpu_ms": poll_cpu, "wall_ms": poll_wall, "polls": args.polls},
        })
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    for row in out["sizes"]:
        print(row["records"], row["bytes"], row["after_0_limit_100"], row["after_end"], row["poll_no_new_avg"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
