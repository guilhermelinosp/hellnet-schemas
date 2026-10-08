"""Redpanda Schema Registry sync against a local fake registry (no network)."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import redpanda_registry as r

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


class Fake(BaseHTTPRequestHandler):
    subjects, configs, compatible, calls = {}, {}, True, []

    def log_message(self, *args):
        pass

    def reply(self, code, body=None):
        raw = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"null")

    def do_GET(self):
        Fake.calls.append(("GET", self.path))
        subject = self.path.split("/")[2]
        self.reply(200, {"id": 1}) if subject in Fake.subjects else self.reply(404, {"error_code": 40401})

    def do_POST(self):
        Fake.calls.append(("POST", self.path))
        if self.path.startswith("/compatibility/"):
            return self.reply(200, {"is_compatible": Fake.compatible})
        Fake.subjects[self.path.split("/")[2]] = self.body()
        self.reply(200, {"id": len(Fake.subjects)})

    def do_PUT(self):
        Fake.calls.append(("PUT", self.path))
        Fake.configs[self.path.split("/")[2]] = self.body()["compatibility"]
        self.reply(200, {})


class RegistryTests(unittest.TestCase):
    def setUp(self):
        Fake.subjects, Fake.configs, Fake.compatible, Fake.calls = {}, {}, True, []
        self.server = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def test_check_accepts_new_subjects_without_writing(self):
        r.sync(self.url, SCHEMAS, apply=False)
        self.assertFalse([c for c in Fake.calls if c[0] != "GET"])

    def test_check_rejects_incompatible_schema(self):
        Fake.subjects["fast.order.requested.v1"] = {}
        Fake.compatible = False
        with self.assertRaisesRegex(ValueError, "is not [A-Z]+-compatible"):
            r.sync(self.url, SCHEMAS, apply=False)

    def test_apply_sets_compatibility_and_registers_every_contract(self):
        r.sync(self.url, SCHEMAS, apply=True)
        self.assertEqual(set(Fake.subjects), {f"fast.order.{e}.v1" for e in ("requested", "accepted", "cancelled", "completed")})
        declared = {json.loads(m.read_text())["compatibility"] for m in SCHEMAS.glob("**/v*/.meta.json")}
        self.assertEqual(set(Fake.configs.values()), declared)
        self.assertEqual(Fake.subjects["fast.order.requested.v1"]["schemaType"], "AVRO")

    def test_rejects_credentials_in_url(self):
        with self.assertRaisesRegex(ValueError, "invalid Registry base URL"):
            r.sync("https://user:pw@schema.example", SCHEMAS, apply=False)


if __name__ == "__main__":
    unittest.main()
