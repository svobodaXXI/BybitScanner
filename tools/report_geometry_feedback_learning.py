"""Create a read-only report from archived Scanner signals and owner reviews.

Never loads or changes PAPER DB, Scanner, Robot or active detector parameters.
Output remains unpartitioned and cannot authorize training or promotion.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geometry_feedback_learning_report import (
    GeometryLearningReportError, build_geometry_learning_report,
    write_geometry_learning_report,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal-id", action="append", default=None,
                        help="Optional exact signal ID; repeat for a subset. Omit to discover all reviews")
    parser.add_argument("--output", required=True, type=Path, help="New report JSON; never overwrite")
    parser.add_argument("--signal-archive-dir", type=Path, default=None)
    parser.add_argument("--feedback-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        report = build_geometry_learning_report(
            args.signal_id, archive_directory=args.signal_archive_dir, feedback_dir=args.feedback_dir,
        )
        write_geometry_learning_report(report, args.output)
    except (GeometryLearningReportError, OSError, ValueError) as exc:
        parser.error(f"no learning report published: {exc}")
    summary = report["summary"]
    print(f"Owner feedback report: {summary['eligible_signals']} eligible signals; "
          f"{summary['corrected']} corrected, {summary['confirmed']} confirmed, "
          f"{summary['false_positive']} false positive, {report['skipped_uncertain']} uncertain skipped")
    print("OFFLINE_DIAGNOSTICS_ONLY — detector not trained, holdout not assigned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
