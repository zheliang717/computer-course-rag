from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).parent / "dist"
API_HOST = os.getenv("API_UPSTREAM_HOST", "api")
API_PORT = int(os.getenv("API_UPSTREAM_PORT", "8000"))
PUBLIC_PREVIEW = os.getenv("PUBLIC_PREVIEW", "false").lower() == "true"
MAX_PROXY_BODY = 40 * 1024 * 1024
HOP_HEADERS = {"connection", "content-length", "host", "keep-alive", "proxy-authenticate",
               "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


class SpaHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        if PUBLIC_PREVIEW and any(part.startswith('.') for part in unquote(urlsplit(self.path).path).split('/') if part):
            # Do not turn secret-looking dot paths into successful SPA pages.
            self.send_error(404, 'Not found')
            return None
        path = Path(self.translate_path(self.path))
        if not path.exists() or path.is_dir() and not (path / "index.html").exists():
            # Missing versioned JS/CSS must not become a successful HTML response.
            # Only extensionless application routes get the SPA document fallback.
            requested = urlsplit(self.path).path
            if requested.startswith('/assets/') or Path(requested).suffix:
                self.send_error(404, 'Static asset not found')
                return None
            self.path = "/index.html"
        return super().send_head()

    def send_response(self, code, message=None):
        self._response_code = code
        return super().send_response(code, message)

    def end_headers(self):
        path = urlsplit(self.path).path
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        if PUBLIC_PREVIEW:
            self.send_header('Strict-Transport-Security', 'max-age=86400')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
            self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        if path.startswith('/api/v1/') or path == '/health':
            self.send_header('Cache-Control', 'private, no-store, no-transform')
        if not path.startswith('/api/v1/') and path != '/health':
            if path.startswith('/assets/') and getattr(self, '_response_code', None) in (200, 304):
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            else:
                self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def _proxy_api(self) -> bool:
        path = urlsplit(self.path).path
        if not (path.startswith("/api/v1/") or path == "/health"):
            return False
        if self.headers.get('Transfer-Encoding'):
            self.close_connection = True
            self.send_error(400, 'Transfer encoding is not supported')
            return True
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.close_connection = True
            self.send_error(400, 'Invalid content length')
            return True
        if length < 0 or length > MAX_PROXY_BODY:
            self.close_connection = True
            self.send_error(413, "Request too large")
            return True
        body = self.rfile.read(length) if length else None
        origin=self.headers.get('Origin')
        if self.command not in {'GET','HEAD','OPTIONS'} and origin and urlsplit(origin).netloc.lower()!=self.headers.get('Host','').lower():
            self.send_error(403,'Cross-origin write refused')
            return True
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in HOP_HEADERS and key.lower() != "origin"}
        headers['X-Forwarded-Proto']='https' if PUBLIC_PREVIEW else 'http'
        connection = HTTPConnection(API_HOST, API_PORT, timeout=120)
        response_started = False
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            if response.getheader("Content-Type", "").startswith("text/event-stream"):
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in HOP_HEADERS:
                        self.send_header(key, value)
                self.send_header("Connection", "close")
                self.end_headers()
                response_started = True
                self.close_connection = True
                while self.command != "HEAD":
                    chunk = response.read1(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                return True
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except OSError:
            if not response_started:
                self.send_error(502, "API temporarily unavailable")
        finally:
            connection.close()
        return True

    def do_GET(self):
        if not self._proxy_api():
            super().do_GET()

    def do_HEAD(self):
        if not self._proxy_api():
            super().do_HEAD()

    def do_POST(self):
        if not self._proxy_api():
            self.send_error(404)

    def do_PATCH(self):
        if not self._proxy_api():
            self.send_error(404)

    def do_PUT(self):
        if not self._proxy_api():
            self.send_error(404)

    def do_DELETE(self):
        if not self._proxy_api():
            self.send_error(404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", int(os.getenv('PORT','80'))), SpaHandler)
    server.serve_forever()
