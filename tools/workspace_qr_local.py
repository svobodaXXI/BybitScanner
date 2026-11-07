"""Generate a local-only QR file for a validated HTTPS workspace URL.

This command never certifies server readiness or authorization and does not send
Telegram notifications. Public delivery remains gated by a real Access check.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from workspace_ready_link import workspace_link, write_workspace_qr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    url = workspace_link(args.origin, args.mode, args.symbol, args.timeframe)
    output = write_workspace_qr(url, Path(args.destination))
    print("QR_FILE=" + str(output))
    print("SECURITY_STATUS=UNVERIFIED_REMOTE_ACCESS")


if __name__ == "__main__":
    main()
