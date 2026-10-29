"""
Incremental Update Distribution Server
Provides reliable HTTP/HTTPS hosting for manifests and chunked file downloads,
supporting local development, integration testing, and production deployment.
"""

import os
import sys
import threading
import socketserver
import http.server
import argparse
from typing import Optional, Tuple


class UpdateHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler with CORS headers and proper MIME streaming."""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        # Silent or concise logging for tests
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_update_server(serve_directory: str, port: int = 0) -> Tuple[http.server.HTTPServer, int, threading.Thread]:
    """
    Start a background update server on an ephemeral or specific port.
    Returns (server, actual_port, thread).
    """
    serve_directory = os.path.abspath(serve_directory)

    class CustomHandler(UpdateHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=serve_directory, **kwargs)

    server = ThreadedHTTPServer(("127.0.0.1", port), CustomHandler)
    actual_port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    return server, actual_port, thread


def main():
    parser = argparse.ArgumentParser(description="Run RemoteConnect Incremental Update Server")
    parser.add_argument("--dir", default="./releases", help="Directory containing release files and manifests")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")

    args = parser.parse_args()
    abs_dir = os.path.abspath(args.dir)
    os.makedirs(abs_dir, exist_ok=True)

    server, port, _ = start_update_server(abs_dir, args.port)
    print(f"============================================================")
    print(f"  RemoteConnect Incremental Update Server Active")
    print(f"  Serving: {abs_dir}")
    print(f"  URL: http://127.0.0.1:{port}/")
    print(f"  Manifest: http://127.0.0.1:{port}/manifest.json")
    print(f"============================================================")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down update server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
