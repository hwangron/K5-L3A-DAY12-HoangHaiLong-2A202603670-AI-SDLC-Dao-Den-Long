"""Open the playable game: python3 serve.py  (serves this folder, opens the browser)."""
import functools
import http.server
import os
import socketserver
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{port}/web/"
        print(f"Dao Den Long: {url}  (Ctrl+C to stop)")
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
