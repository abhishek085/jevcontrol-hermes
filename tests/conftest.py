"""Load the plugin as the package `jev_control` (the repo directory name has a hyphen), with no Hermes install needed."""

import importlib.util
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
_spec = importlib.util.spec_from_file_location("jev_control", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
_pkg = importlib.util.module_from_spec(_spec)
sys.modules["jev_control"] = _pkg
_spec.loader.exec_module(_pkg)

DEFAULTS = {"spark_url": "", "spark_model": "test-model", "spark_api": "decide", "jev_timeout_s": 5,
            "privacy_tau": 0.8, "memory_tau": 0.7, "search_tau": 0.15, "search_min_keep": 2, "search_max_keep": 10,
            "guard_approve_tau": 0.9, "guard_deny_tau": 0.7, "compress_need_tau": 0.5, "compress_trim_chars": 4000,
            "compress_threshold": 0.5, "compress_keep_last": 2, "compress_threshold_tokens": 0}


@pytest.fixture
def cfg():
    """Settings lookup like the plugin's `_cfg`; tests mutate the dict to change a setting."""
    return _Cfg(dict(DEFAULTS))


class _Cfg:
    def __init__(self, d):
        self.d = d

    def __call__(self, key):
        return self.d.get(key)

    def __setitem__(self, k, v):
        self.d[k] = v


class FakeJev:
    """Stands in for jev_control.jev_client.Jev: returns scripted picks / yes-probabilities."""

    def __init__(self, pick="public", p=0.99, yes=None):
        self.pick, self.p, self.yes, self.calls = pick, p, yes, []

    def choice(self, state, instructions, options):
        self.calls.append(("choice", state))
        return {"pick": self.pick, "p": self.p, "probs": {self.pick: self.p}, "ms": 1.0}

    def yes_probs(self, state, instructions):
        self.calls.append(("yes", state))
        return (self.yes if self.yes is not None else [0.99] * len(instructions)), 1.0


@pytest.fixture
def fake_jev():
    return FakeJev


@pytest.fixture
def serve():
    """Start a throwaway HTTP server: serve({path: handler(body) -> (status, json)}) -> base url like http://127.0.0.1:PORT."""
    servers = []

    def start(routes):
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                status, obj = routes[self.path](body)
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()
