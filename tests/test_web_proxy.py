"""The packaged web server serves API calls from the same browser origin."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen

from frontend import server as web_server


class _Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        self._reply({"method": "GET", "path": self.path})

    def do_POST(self):
        payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self._reply({"method": "POST", "path": self.path, "authorization": self.headers.get("Authorization"),
                     "content_type": self.headers.get("Content-Type"), "body": payload.decode()})

    def _reply(self, data):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def test_same_origin_web_proxy_forwards_auth_body_and_query(monkeypatch) -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    monkeypatch.setattr(web_server, "API_HOST", "127.0.0.1")
    monkeypatch.setattr(web_server, "API_PORT", upstream.server_port)
    frontend = ThreadingHTTPServer(("127.0.0.1", 0), web_server.SpaHandler)
    threads = [Thread(target=server.serve_forever, daemon=True) for server in (upstream, frontend)]
    for thread in threads:
        thread.start()
    try:
        base = f"http://127.0.0.1:{frontend.server_port}"
        with urlopen(f"{base}/health") as response:
            assert json.load(response) == {"method": "GET", "path": "/health"}
        request = Request(f"{base}/api/v1/example?limit=2", method="POST", data=b'{"value":1}',
                          headers={"Authorization": "Bearer test", "Content-Type": "application/json"})
        with urlopen(request) as response:
            assert json.load(response) == {"method": "POST", "path": "/api/v1/example?limit=2",
                                           "authorization": "Bearer test", "content_type": "application/json",
                                           "body": '{"value":1}'}
    finally:
        for server in (frontend, upstream):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
