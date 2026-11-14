"""Same-origin, explicit-file-only short trades chart POST; no permanent data."""
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import json
import unittest
from urllib.parse import urlencode

from research.local_replay_viewer.server import handler_factory


class ExplicitFineArchiveHttpTests(unittest.TestCase):
    @contextmanager
    def server(self):
        with TemporaryDirectory() as directory:
            httpd = ThreadingHTTPServer(("127.0.0.1",0),
                handler_factory(Path(directory)))
            thread = Thread(target=httpd.serve_forever,daemon=True)
            thread.start()
            try: yield httpd.server_address[1]
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)

    def call(self, port:int, archive:bytes, *, permitted:bool):
        start = int(datetime(2026,11,10,8,tzinfo=timezone.utc).timestamp()*1000)
        query = urlencode({"symbol":"ICNTUSDT","filename":"ICNTUSDT2026-11-10.csv.gz",
            "start_ms":str(start),"end_ms":str(start+60_000)})
        conn = HTTPConnection("127.0.0.1",port,timeout=5)
        headers = {"Content-Type":"application/octet-stream",
            "X-Local-Chart-Import":"explicit-owner-file",
            "Origin":f"http://127.0.0.1:{port}" if permitted else "https://example.com"}
        try:
            conn.request("POST","/local-replay/chart-trades?"+query,
                body=archive,headers=headers)
            resp=conn.getresponse()
            return resp.status,resp.read()
        finally: conn.close()

    def test_only_explicit_same_origin_archive_derives_public_candles(self):
        start = int(datetime(2026,11,10,8,tzinfo=timezone.utc).timestamp()*1000)
        raw = ("timestamp,symbol,price,size,trdMatchID\n"+
            f"{start/1000:.3f},ICNTUSDT,1.0,2,t1\n"+
            f"{(start+15_000)/1000:.3f},ICNTUSDT,1.1,3,t2\n").encode()
        archive = gzip.compress(raw,mtime=0)
        with self.server() as port:
            bad,_=self.call(port,archive,permitted=False)
            self.assertEqual(bad,403)
            good,data=self.call(port,archive,permitted=True)
        self.assertEqual(good,200)
        parsed=json.loads(data)
        self.assertEqual(parsed["symbol"],"ICNTUSDT")
        self.assertEqual(len(parsed["m1"]),1)
        self.assertEqual(len(parsed["s15"]),2)
        self.assertEqual(parsed["missing_15s"],2)
        self.assertFalse(parsed["pinned_original_icnt"])
        self.assertTrue(parsed["l2_executions_unchanged"])


if __name__ == "__main__":
    unittest.main()
