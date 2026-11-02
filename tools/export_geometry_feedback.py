"""Export explicitly selected owner-reviewed Scanner signals for offline analysis.

No training, parameter promotion, Scanner runtime interaction, or PAPER DB access.
Run from a checked-out repository only after source and feedback archives exist.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geometry_feedback_export import GeometryExportError, export_reviewed_examples


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-id", action="append", required=True,
                        help="Exact archived signal_id; repeat for selected reviews")
    parser.add_argument("--output", type=Path, required=True, help="New JSONL file; never overwritten")
    parser.add_argument("--signal-archive-dir", type=Path, default=None)
    parser.add_argument("--feedback-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        count = export_reviewed_examples(
            args.signal_id, args.output, archive_directory=args.signal_archive_dir,
            feedback_directory=args.feedback_dir,
        )
    except (GeometryExportError, OSError, ValueError) as exc:
        parser.error(f"no training corpus exported: {exc}")
    print(f"Exported {count} independently reviewed source signal(s); split UNASSIGNED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
