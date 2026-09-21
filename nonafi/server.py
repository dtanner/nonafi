"""HTTP server: static UI, artist JSON, cover images, audio with Range support."""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .library import Library

STATIC = Path(__file__).parent / "static"
MIME = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}


def set_output_full() -> None:
    """Volume is controlled on the speakers, so give them the full signal."""
    try:
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "1.0"], timeout=3)
        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], timeout=3)
    except Exception:
        pass


class Events:
    """Fan-out of UI commands (from the voice service) to connected pages via SSE."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=32)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, obj: dict) -> int:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(obj)
            except queue.Full:
                pass
        return len(subs)


class Handler(BaseHTTPRequestHandler):
    library: Library
    events = Events()
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("NONAFI_DEBUG"):
            super().log_message(fmt, *args)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._file(STATIC / "index.html", "text/html; charset=utf-8", cache=False)
        if path == "/api/artists":
            self.library.refresh_if_changed()
            return self._json(self.library.to_json())
        if path == "/api/events":
            return self._events()
        if path.startswith("/covers/"):
            aid = path[len("/covers/"):].split(".")[0].split("-")[0]
            artist = self.library.artists.get(aid)
            if artist and artist.cover:
                return self._bytes(artist.cover, "image/jpeg")
            return self._error(HTTPStatus.NOT_FOUND)
        if path.startswith("/audio/"):
            tid = path[len("/audio/"):].split(".")[0]
            track = self.library.tracks.get(tid)
            if track and track.path.exists():
                return self._file(track.path, MIME.get(track.path.suffix.lower(), "application/octet-stream"))
            return self._error(HTTPStatus.NOT_FOUND)
        if "/.." not in path and (STATIC / path.lstrip("/")).is_file():
            f = STATIC / path.lstrip("/")
            return self._file(f, mimetypes.guess_type(str(f))[0] or "application/octet-stream", cache=False)
        return self._error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length > 4096:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST)
        if path == "/api/rescan":
            self.library._signature = None
            changed = self.library.refresh_if_changed()
            return self._json({"artists": len(self.library.artists), "changed": changed})
        if path == "/api/command":
            # From the voice service: {"action": "play"|"pause"|"next"|"play_artist"|"listening"|"heard", ...}
            if not isinstance(body, dict) or not body.get("action"):
                return self._error(HTTPStatus.BAD_REQUEST)
            return self._json({"clients": self.events.publish(body)})
        return self._error(HTTPStatus.NOT_FOUND)

    # --- helpers -------------------------------------------------------

    def _events(self):
        """Server-sent events: one JSON object per message, keepalive comments every 15s."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        q = self.events.subscribe()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    obj = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.events.unsubscribe(q)

    def _json(self, obj):
        self._bytes(json.dumps(obj).encode(), "application/json", cache=False)

    def _error(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _bytes(self, data: bytes, ctype: str, cache=True):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, ctype: str, cache=True):
        size = path.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):
                    start = max(0, size - int(m.group(2)))
                if start > end or start >= size:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                partial = True
        length = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    music = Path(os.environ.get("NONAFI_MUSIC", "~/Music")).expanduser()
    port = int(os.environ.get("NONAFI_PORT", "8080"))
    host = os.environ.get("NONAFI_HOST", "127.0.0.1")
    for i, a in enumerate(argv):
        if a == "--music":
            music = Path(argv[i + 1]).expanduser()
        if a == "--port":
            port = int(argv[i + 1])
        if a == "--host":
            host = argv[i + 1]
    lib = Library(music)
    lib.refresh_if_changed()
    Handler.library = lib
    set_output_full()
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"nonafi: {len(lib.artists)} artists from {music}, listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
