from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(r"C:\BybitScanner")
CR = ROOT / "DOCUMENTS" / "CHANGE_REQUESTS" / "CR-TRADING-WORKSPACE-001.md"
ROADMAP = ROOT / "DOCUMENTS" / "TRADING_WORKSPACE_MASTER_ROADMAP.md"
STATE = ROOT / "DOCUMENTS" / "PROJECT_STATE.md"

M9_CR = """## 88. M9 — Workspace Operability / Diagnostics — architecture/documentation checkpoint

Status: `DOCUMENTED / IMPLEMENTATION NOT YET CLAIMED`

Purpose: make Workspace failures diagnosable and operationally deterministic without reopening the completed M0–M8 market-data architecture.

Binding invariants:

1. Preserve semantic root causes across subsystem boundaries. Generic `ValueError`, `LookupError`, `unsupported_symbol`, bare HTTP 409, or transport-only `ECONNABORTED` must not erase the actual failure class.
2. Introduce typed Workspace failure semantics for unsupported instrument, candidate-not-ready, instrument/bootstrap failure, inactive Workspace, unknown stream, and upstream market-data failure.
3. User-facing/API failure envelopes must carry structured fields sufficient for diagnosis, including `code`, `stage`, `requested_symbol`, `active_symbol`, `retryable`, and a request/correlation identity where applicable.
4. Add read-only Workspace diagnostic state exposing requested/active symbol, generation, pending switch, readiness/component state, latest structured error, and relevant upstream/subscription state.
5. `WorkspaceController` remains the sole authoritative symbol owner. Frontend authoritative symbol transition occurs only after backend activation acknowledgement for the new generation; failed candidate activation preserves the previous active Workspace.
6. Reconnect policy must distinguish transport-retryable failures from semantic fatal/non-retryable failures. Blind fixed one-second retry loops for semantic failures are prohibited.
7. Provide one deterministic developer doctor command that checks registry support, switch/activation, readiness, stream availability, and structured failure output for a requested symbol/interval.
8. Add registry→Workspace contract verification so a symbol advertised as Workspace-supported must be activatable by the Workspace transport contract; intentionally unsupported symbols must not be presented as supported.
9. Preserve PAPER semantics, full authoritative L2, M0–M8 generation/sequence/readiness guarantees, and unrelated user-owned dirty work.
10. Do not rewrite the server framework or create a second market-data owner. M9 is a thin operability/control-plane slice over the existing architecture.

Expected implementation surfaces are bounded to semantic exceptions/error envelopes, read-only diagnostics, switch acknowledgement semantics, reconnect classification, the doctor command, and focused contract/regression checks.

"""

SECTION14 = """## 14. Current immediate next step

Do not jump ahead.

Current checkpoint:

```text
M8 — COMPLETE / REAL-PHONE ACCEPTANCE PASS
```

Completed corrective migration:

```text
M0–M8 — MARKET DATA HUB + MULTIPLEXED WORKSPACE STREAM
IMPLEMENTED / VERIFIED / REAL-PHONE ACCEPTED
```

The former instruction to begin M0 is superseded. `InstrumentRegistry`, `MarketDataHub`, `WorkspaceController`, efficient snapshot/delta client projection, the multiplexed Workspace WebSocket, atomic frontend generation projection, deterministic chaos/regression coverage, and real-phone acceptance are complete through M8.

Open next bounded work item:

```text
M9 — WORKSPACE OPERABILITY / DIAGNOSTICS
```

M9 must preserve semantic root causes, expose read-only diagnostic state, keep `WorkspaceController` as sole symbol authority, make frontend symbol transition depend on backend activation acknowledgement/new generation, classify reconnect behavior, provide a deterministic developer doctor command, and verify registry→Workspace support consistency.

M9 does not authorize a market-data rewrite, a second state owner, or any change to PAPER/trading semantics. Implementation remains separately gated after this architecture/documentation checkpoint.

Aggressive DOM Limit confirmation and Done/Enter focus progression remain separately deferred.

"""

STATE_APPEND = """# TRADING_WORKSPACE_CURRENT_CHECKPOINT_2026_08_30

Status:

ACTIVE

Authority note:

For Trading Workspace current mission recovery, this checkpoint supersedes older Trading Workspace next-step text in this document when that older text conflicts with the active ChangeRequest or `TRADING_WORKSPACE_MASTER_ROADMAP.md`.

Current authoritative state:

* `CR-TRADING-WORKSPACE-001` revision `1.82`;
* M0–M8 Market Data Hub / multiplexed Workspace migration: COMPLETE;
* M8 desktop + real-phone acceptance: PASS;
* next bounded work item: `M9 — Workspace Operability / Diagnostics`;
* M9 is architecture/documentation-authorized only at this checkpoint; implementation completion is not claimed;
* `WorkspaceController` remains sole symbol authority;
* semantic root causes must survive to the diagnostic/API boundary;
* previous active Workspace must remain authoritative until candidate activation ACK/new generation succeeds;
* reconnect behavior must distinguish transport-retryable from semantic non-retryable failure;
* local dirty implementation remains user-owned and must not be staged, reset, restored, or committed by this documentation checkpoint.

Exact next action:

Implement M9 only after the documentation checkpoint is reviewed and accepted, beginning with typed semantic failure classes + structured diagnostics while preserving M0–M8 behavior.

"""

def read_doc(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError(f"{path}: unexpected UTF-8 BOM; refusing to rewrite")
    text = raw.decode("utf-8")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return text.replace("\r\n", "\n"), newline

def write_doc(path: Path, text_lf: str, newline: str) -> None:
    out = text_lf if newline == "\n" else text_lf.replace("\n", "\r\n")
    path.write_bytes(out.encode("utf-8"))

def require(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)

def update_cr() -> None:
    text, nl = read_doc(CR)
    if '"revision": "1.82"' not in text:
        require('"revision": "1.81"' in text, "CR revision 1.81 anchor not found")
        text = text.replace('"revision": "1.81"', '"revision": "1.82"', 1)
    if "## 88. M9 — Workspace Operability / Diagnostics" not in text:
        text = text.rstrip() + "\n\n" + M9_CR
    write_doc(CR, text, nl)

def update_roadmap() -> None:
    text, nl = read_doc(ROADMAP)
    pattern = r"(?ms)^## 14\. Current immediate next step\s*$.*?(?=^## 15\. Engineering completion criterion\s*$)"
    matches = list(re.finditer(pattern, text))
    require(len(matches) == 1, f"Roadmap section 14 anchor count = {len(matches)}, expected 1")
    text = re.sub(pattern, SECTION14, text, count=1)

    # Remove the known stale future-track sentence if present without requiring it.
    text = text.replace(
        "This future track does not change section 14's immediate next step.",
        "This future track does not change the current M9 immediate next step.",
    )
    write_doc(ROADMAP, text, nl)

def update_state() -> None:
    text, nl = read_doc(STATE)
    if re.search(r"(?m)^7\.66$", text) is None:
        require(re.search(r"(?m)^7\.65$", text) is not None, "PROJECT_STATE version 7.65 anchor not found")
        text = re.sub(r"(?m)^7\.65$", "7.66", text, count=1)
    # First Date field only.
    text = re.sub(r"(?ms)(^Date:\s*\n\s*)2026-08-26(\s*$)", r"\g<1>2026-08-30\2", text, count=1)
    if "# TRADING_WORKSPACE_CURRENT_CHECKPOINT_2026_08_30" not in text:
        text = text.rstrip() + "\n\n---\n\n" + STATE_APPEND
    write_doc(STATE, text, nl)

def main() -> int:
    for p in (CR, ROADMAP, STATE):
        require(p.is_file(), f"Missing required file: {p}")
    update_cr()
    update_roadmap()
    update_state()
    print("PASS: documentation update applied")
    print("Changed scope:")
    print(f"  {CR}")
    print(f"  {ROADMAP}")
    print(f"  {STATE}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
