import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "atlantis", "--db", str(Path(cls.directory.name) / "city.db"),
             "--env", str(Path(cls.directory.name) / "missing.env"), "serve", "--port", "0"],
            cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        line = cls.process.stdout.readline().strip()
        if not line.startswith("Atlantis: http://127.0.0.1:"):
            cls.process.terminate()
            cls.process.wait(timeout=5)
            raise RuntimeError("Test observation server did not start.")
        cls.base = line.split("Atlantis: ", 1)[1]

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.communicate(timeout=5)
        cls.directory.cleanup()

    def request(self, path, body=None, headers=None):
        request = Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                          headers=headers or ({"Content-Type": "application/json"} if body is not None else {}))
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_observation_server_completes_a_background_experiment(self):
        run = self.request("/api/runs", {"agent_count": 1})["id"]
        self.request(f"/api/runs/{run}/start", {})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = self.request(f"/api/runs/{run}")
            if state["status"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(state["status"], "completed")
        self.assertTrue(state["scores"]["task-1"]["passed"])

    def test_cross_origin_mutations_are_rejected(self):
        with self.assertRaises(HTTPError) as captured:
            self.request("/api/runs", {}, {"Content-Type": "application/json", "Origin": "https://example.com"})
        self.assertEqual(captured.exception.code, 403)

    def test_rebinding_host_is_rejected(self):
        with self.assertRaises(HTTPError) as captured:
            self.request("/api/runs", headers={"Host": "example.com"})
        self.assertEqual(captured.exception.code, 403)

    def test_static_page_and_configuration_are_available(self):
        with urlopen(self.base, timeout=3) as response:
            self.assertIn("Atlantis", response.read().decode())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        config = self.request("/api/capabilities")
        self.assertNotIn("token", config)


if __name__ == "__main__":
    unittest.main()
