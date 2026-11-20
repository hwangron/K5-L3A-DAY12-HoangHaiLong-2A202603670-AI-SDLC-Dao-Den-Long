"""Play the game: python3 serve.py [port] [--no-browser]   (serves this folder, opens the browser).

Also the small local API used by the web page (Ticket-04):
  GET  /api/leaderboard             -> {"entries": [...]}
  POST /api/leaderboard             {name, score, nights_won, seed} -> {"entries": [...], "rank": n|null}
                                    400 {"error": "..."} when the entry is invalid
  POST /api/bench                   only when bench.py runs the server (make_server(bench_sink=...))
python3 serve.py --export-leaderboard out.json   writes {"entries": [...]} (rank order) and exits, no server.
The leaderboard file is $DDL_LEADERBOARD, default ~/.dao-den-long/leaderboard.json.
"""
import argparse
import functools
import http.server
import json
import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from game import leaderboard  # noqa: E402

MAX_BODY = 64 * 1024               # leaderboard POST
MAX_BENCH_BODY = 32 * 1024 * 1024  # bench POST: one dt per frame for the whole run


class Handler(http.server.SimpleHTTPRequestHandler):
    # Windows' registry can map .js to text/plain, which breaks module scripts and Pyodide.
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map)
    extensions_map.update({".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
                           ".wasm": "application/wasm", ".zip": "application/zip", ".whl": "application/zip",
                           ".svg": "image/svg+xml", ".html": "text/html", ".css": "text/css"})
    bench_sink = None                # set per server by make_server

    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self, limit):
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise ValueError("Content-Length required")
        if n < 0 or n > limit:
            raise ValueError("body too large")
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("body must be valid JSON")

    def _route(self):
        return self.path.split("?", 1)[0].rstrip("/")

    def do_GET(self):
        if self._route() == "/api/leaderboard":
            self._send_json(200, {"entries": leaderboard.load()})
        else:
            super().do_GET()

    def do_POST(self):
        route = self._route()
        if route == "/api/leaderboard":
            try:
                entries, rank = leaderboard.add(self._read_json(MAX_BODY))
            except (ValueError, OSError) as e:       # LeaderboardError is a ValueError
                code = 500 if isinstance(e, OSError) else 400
                return self._send_json(code, {"error": str(e)})
            self._send_json(200, {"entries": entries, "rank": rank})
        elif route == "/api/bench" and self.bench_sink is not None:
            try:
                data = self._read_json(MAX_BENCH_BODY)
                if not isinstance(data, dict):
                    raise ValueError("bench result must be a JSON object")
                data.setdefault("user_agent", self.headers.get("User-Agent", ""))
                self.bench_sink(data)
            except ValueError as e:
                return self._send_json(400, {"error": str(e)})
            self._send_json(200, {"ok": True})
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        if getattr(self.server, "quiet", False):
            return
        super().log_message(fmt, *args)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second process bind a port that is already being served.
    allow_reuse_address = os.name != "nt"
    quiet = False

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return      # the browser closed the connection (e.g. the bench window was closed): not worth a traceback
        super().handle_error(request, client_address)


def make_server(port=0, bench_sink=None, host="127.0.0.1", quiet=False):
    """HTTP server for this folder + the API. port 0 = any free port (see server.server_address[1]).
    bench_sink(dict) enables POST /api/bench. Call serve_forever() / shutdown() / server_close() yourself."""
    handler = type("BoundHandler", (Handler,), {"bench_sink": staticmethod(bench_sink) if bench_sink else None})
    httpd = Server((host, port), functools.partial(handler, directory=ROOT))
    httpd.quiet = quiet
    return httpd


def export_leaderboard(out_path):
    entries = leaderboard.load()
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dao Den Long: serve the game and its local API")
    ap.add_argument("port", nargs="?", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--export-leaderboard", metavar="FILE",
                    help="write the leaderboard as {\"entries\": [...]} to FILE and exit")
    a = ap.parse_args(argv)
    if a.export_leaderboard:
        try:
            export_leaderboard(a.export_leaderboard)
        except OSError as e:
            sys.stderr.write(f"error: cannot write {a.export_leaderboard}: {e}\n")
            return 1
        return 0
    with make_server(a.port) as httpd:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/web/"
        print(f"Dao Den Long: {url}  (Ctrl+C to stop)")
        if not a.no_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
