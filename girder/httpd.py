import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .api import API
from .errors import Rejected
from .jsonwire import canonical, parse_json

ROOT = Path(__file__).resolve().parent.parent
ASSETS = re.compile(r"/web/(?:css/)?[a-z-]+\.(css|js)\Z")
TYPES = {"css": "text/css; charset=utf-8", "js": "text/javascript; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, data, media_type, status=200, attachment=None):
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(data)

    def json(self, value, status=200, attachment=None):
        self.send_bytes(canonical(value).encode(), "application/json; charset=utf-8", status, attachment)

    def serve(self, write=False):
        try:
            route = urlsplit(self.path)
            if write:
                if self.headers.get_content_type() != "application/json":
                    raise Rejected("请求类型须为 JSON", 415)
                length = self.headers.get("Content-Length", "")
                if not re.fullmatch(r"[0-9]{1,9}", length) or not 1 <= int(length) <= 1_050_000:
                    raise Rejected("导入包大小非法或超限", 413)
                self.json(self.server.api.write(route.path, parse_json(self.rfile.read(int(length)))))
            elif route.path.startswith("/api/"):
                body, attachment = self.server.api.read(route.path, route.query)
                self.json(body, attachment=attachment)
            else:
                self.asset(route.path)
        except Rejected as exc:
            self.json({"error": str(exc)}, exc.status)
        except (ValueError, TimeoutError):
            self.json({"error": "请求目标或内容无效"}, 400)
        except sqlite3.OperationalError as exc:
            self.log_error("SQLite: %s", exc)
            self.json({"error": "存储暂不可用，请稍后重试"}, 503)

    def asset(self, path):
        if path == "/":
            self.send_bytes((ROOT / "web/index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/example":
            directory = ROOT / "examples"
            self.json(dict(plan=parse_json((directory / "plan.json").read_bytes()),
                           positions=(directory / "positions.csv").read_text(),
                           readings=(directory / "readings.csv").read_text()))
            return
        if path == "/example-graded":
            directory = ROOT / "examples"
            self.json(dict(plan=parse_json((directory / "graded-plan.json").read_bytes()),
                           positions=(directory / "graded-positions.csv").read_text(),
                           readings=(directory / "graded-readings.csv").read_text()))
            return
        match = ASSETS.fullmatch(path)
        if match and (ROOT / path[1:]).is_file():
            self.send_bytes((ROOT / path[1:]).read_bytes(), TYPES[match[1]])
            return
        raise Rejected("找不到页面资源", 404)

    def do_GET(self):
        self.serve()

    def do_POST(self):
        self.serve(write=True)


class Server(ThreadingHTTPServer):
    def __init__(self, address, store):
        self.api = API(store)
        super().__init__(address, Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        return connection, address
