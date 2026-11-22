"""Unprivileged transport for a Gateway-signed receipt, not an authority."""
import json
import os
from pathlib import Path
import re
import tempfile

SPOOL = Path("/var/lib/bybitscanner")
CALLBACK = re.compile(r"rel:([ar]):([0-9a-f]{32})\Z")


def relay(update, *, spool=SPOOL):
    """Write only one bounded envelope per proposal. Root re-verifies everything."""
    q = update.get("callback_query") or {}
    data = q.get("data")
    match = CALLBACK.fullmatch(data) if type(data) is str else None
    if not match:
        return False
    envelope = update.get("_release_approval")
    if type(envelope) is not dict or type(envelope.get("payload")) is not dict:
        return False
    p = envelope["payload"]
    if (p.get("request_id") != match[2] or p.get("update_id") != update.get("update_id")
            or p.get("decision") != ("approve" if match[1] == "a" else "reject")):
        return False
    raw = json.dumps(envelope, ensure_ascii=True, sort_keys=True, allow_nan=False).encode("ascii")
    if len(raw) > 2048:
        return False
    destination = spool / ("owner-release-" + match[2] + ".json")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=spool, prefix=".owner-release-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # The first delivered decision wins. Never overwrite with a later click.
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            return False
        fd = os.open(spool, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
