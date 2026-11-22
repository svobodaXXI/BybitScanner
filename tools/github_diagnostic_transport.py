"""Fixed public GitHub transport for authenticated diagnostic envelopes.

No default credentials, service, scheduling, or automatic activation.
The request callable and token must be supplied by a separately trusted host.
"""
from datetime import datetime, timezone
import json

from tools import github_diagnostic_protocol as protocol
from tools.github_status_reporter import ISSUE_URL

REQUEST_MARKER = "BYBITSCANNER_DIAGNOSTIC_REQUEST_V1\n"
RESPONSE_MARKER = "BYBITSCANNER_DIAGNOSTIC_RESPONSE_V1\n"
PAGE_SIZE = 100
MAX_PAGES = 3
MAX_BODY = 8 * 1024 * 1024


class GitHubDiagnosticTransport:
    def __init__(self, *, request, token):
        if (type(token) is not str or not 30 <= len(token) <= 256
                or not token.isascii() or any(c.isspace() for c in token)):
            raise ValueError("invalid protected transport credential")
        self._request = request
        self._headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _exchange(self, method, expected, **kwargs):
        with self._request(method, ISSUE_URL, headers=self._headers,
                           timeout=(3, 8), allow_redirects=False,
                           stream=True, **kwargs) as response:
            if response.status_code != expected:
                raise ValueError("diagnostic transport outcome unproven")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=16384):
                data.extend(chunk)
                if len(data) > MAX_BODY:
                    raise ValueError("diagnostic transport body exceeds bound")
            return json.loads(data, object_pairs_hook=protocol._unique_pairs)

    def requests(self, now):
        since = datetime.fromtimestamp(max(0, now - protocol.MAX_AGE),
                                       timezone.utc).isoformat().replace("+00:00", "Z")
        wires = []
        for page in range(1, MAX_PAGES + 1):
            comments = self._exchange("GET", 200, params={
                "since": since, "per_page": PAGE_SIZE, "page": page,
            })
            if type(comments) is not list or len(comments) > PAGE_SIZE:
                raise ValueError("invalid diagnostic comment page")
            for entry in comments:
                if type(entry) is not dict:
                    raise ValueError("invalid diagnostic comment")
                body = entry.get("body")
                if type(body) is not str or not body.startswith(REQUEST_MARKER):
                    continue
                payload = body[len(REQUEST_MARKER):]
                if 0 < len(payload) <= protocol.MAX_WIRE and payload.isascii():
                    wires.append(payload.encode("ascii"))
            if len(comments) < PAGE_SIZE:
                return wires
        raise ValueError("diagnostic polling window exceeds bound")

    def post(self, request, response):
        # The caller verifies the exact signed pair before publication.
        body = RESPONSE_MARKER + response.decode("ascii")
        result = self._exchange("POST", 201, json={"body": body})
        return (type(result) is dict and type(result.get("id")) is int
                and result["id"] > 0 and result.get("body") == body)
