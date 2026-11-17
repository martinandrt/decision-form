#!/usr/bin/env python3
"""Serve a decision form locally and wait for the answers.

    python3 serve_form.py decisions.html            # http://127.0.0.1:<port>/?t=<token>
    python3 serve_form.py decisions.html --lan      # also reachable from a phone on the same Wi-Fi
    python3 serve_form.py decisions.html --open     # open the page in the default browser

The page posts the answers back; they are written to decisions.answers.json (or --out), printed to stdout,
and the server exits with code 0. An agent can run this in the background and gets notified on exit.
Exit code 2 = timeout without answers. Every request needs the random token from the printed URL.

Standard library only. --lan serves plain HTTP on your local network: use it on networks you trust.
"""
import argparse
import http.server
import json
import secrets
import socket
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_BODY = 1_000_000


def lan_ip() -> str | None:
    """Best guess of this machine's LAN address (no packet is sent by a UDP connect)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            ip = s.getsockname()[0]
            return None if ip.startswith("127.") else ip
    except OSError:
        return None


def make_handler(page: bytes, token: str, out: Path, done: threading.Event, result: dict):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep stdout for the answers only
            pass

        def _authorized(self) -> bool:
            got = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            return secrets.compare_digest(got, token)

        def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")  # the token is in the URL
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path not in ("/", "/index.html"):
                return self._send(404, b"not found")
            if not self._authorized():
                return self._send(403, b"missing or wrong token: use the full URL printed by serve_form.py")
            self._send(200, page, "text/html; charset=utf-8")

        def do_POST(self):
            if urlparse(self.path).path != "/answers":
                return self._send(404, b"not found")
            if not self._authorized():
                return self._send(403, b"wrong token")
            if done.is_set():
                return self._send(409, b"answers already received")
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 < n <= MAX_BODY:
                return self._send(413, b"body missing or too large")
            try:
                data = json.loads(self.rfile.read(n))
                if not isinstance(data.get("answers"), dict) or not data["answers"]:
                    raise ValueError("no answers")
            except (ValueError, AttributeError):
                return self._send(400, b"invalid answers")
            data["received_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            tmp = out.with_suffix(out.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(out)
            result["data"] = data
            self._send(200, b'{"ok": true}', "application/json")
            done.set()

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Serve a decision form and wait for the answers.")
    ap.add_argument("page", help="the .html built by build_form.py")
    ap.add_argument("--out", help="answers file (default: <page>.answers.json)")
    ap.add_argument("--port", type=int, default=0, help="port (default: a free one)")
    ap.add_argument("--lan", action="store_true", help="listen on all interfaces so a phone on the same network can open it")
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    ap.add_argument("--timeout", type=float, default=60, help="minutes to wait for answers (default 60)")
    a = ap.parse_args(argv)

    src = Path(a.page)
    page = src.read_bytes()
    out = Path(a.out) if a.out else src.with_name(src.stem + ".answers.json")
    token = secrets.token_urlsafe(12)
    done, result = threading.Event(), {}
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    server = http.server.ThreadingHTTPServer((host, a.port), make_handler(page, token, out, done, result))
    port = server.server_address[1]
    local = f"http://127.0.0.1:{port}/?t={token}"
    print(f"Open: {local}", flush=True)
    if a.lan:
        ip = lan_ip()
        print(f"Phone (same Wi-Fi): http://{ip}:{port}/?t={token}" if ip else "LAN address not found; use this machine's IP",
              flush=True)
    print(f"Waiting up to {a.timeout:g} min for answers -> {out}", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if a.open:
        webbrowser.open(local)
    try:
        answered = done.wait(a.timeout * 60)
    except KeyboardInterrupt:
        answered = False
    server.shutdown()
    if not answered:
        print("No answers before the timeout.", flush=True)
        return 2
    data = result["data"]
    print(f"Answers: {data.get('code', '')}")
    for r in data.get("readable", []):
        note = f" ({r['note']})" if r.get("note") else ""
        print(f"  {r['question']}. {r['title']} -> {r['choice']}) {r['option']}{note}")
    print(f"Saved: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
