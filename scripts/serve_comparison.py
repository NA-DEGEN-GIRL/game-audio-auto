"""Read-only loopback player for an explicit audio comparison catalog."""

import argparse
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def resolve_audio(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix.lower() not in {".wav", ".mp3", ".ogg"}:
        raise ValueError("Audio must be inside the delivery directory")
    return path


def make_handler(web, deliveries, catalog):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_GET(self, head=False):
            if self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
                self.send_error(403)
                return
            route = urlsplit(self.path).path
            if route == "/api/catalog":
                try:
                    data = json.loads(catalog.read_text(encoding="utf-8"))
                    data["app"] = "game-audio-comparison"
                    # Only audio IDs reach the browser; disk paths stay server-side.
                    for item in data["tracks"]:
                        for mode in ("original", "matched"):
                            if item.get(mode):
                                item[mode] = f"/audio/{item['id']}/{mode}"
                    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
                except (OSError, ValueError, KeyError):
                    self.send_error(503, "Catalog unavailable")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if not head:
                    self.wfile.write(payload)
                return
            static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if route in static:
                path = web / static[route]
            else:
                match = re.fullmatch(r"/audio/([a-zA-Z0-9_-]+)/(original|matched)", route)
                if not match:
                    self.send_error(404)
                    return
                try:
                    data = json.loads(catalog.read_text(encoding="utf-8"))
                    track = next(t for t in data["tracks"] if t["id"] == match[1])
                    path = resolve_audio(deliveries, track[match[2]])
                except (OSError, ValueError, KeyError, StopIteration, TypeError):
                    self.send_error(404)
                    return
            try:
                stream = path.open("rb")
            except OSError:
                self.send_error(404)
                return
            with stream:
                size = path.stat().st_size
                start, end, partial = 0, size - 1, False
                requested = self.headers.get("Range")
                if requested:
                    match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                    try:
                        if not match or not any(match.groups()):
                            raise ValueError
                        if not match[1]:
                            start = max(0, size - int(match[2]))
                        else:
                            start = int(match[1])
                            if match[2]:
                                end = min(end, int(match[2]))
                        if start > end or start >= size:
                            raise ValueError
                    except ValueError:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    partial = True
                self.send_response(206 if partial else 200)
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                if path.suffix == ".js":
                    mime = "text/javascript"
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if not head:
                    stream.seek(start)
                    remaining = end - start + 1
                    try:
                        while remaining:
                            block = stream.read(min(262144, remaining))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass

    return Handler


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--catalog", type=Path, default=root / ".assets/deliveries/themepark-comparison-20260915/catalog.json")
    args = parser.parse_args()
    handler = make_handler(root / "web", root / ".assets/deliveries", args.catalog)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Audio comparison ready: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
