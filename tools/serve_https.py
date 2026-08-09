#!/usr/bin/env python3
"""HTTPS dev server for the web build.

Godot web exports require a secure context; http://<LAN-IP> is not one, so
on-device testing (iPhone Safari) needs HTTPS. Uses the self-signed cert in
.certs/ — Safari shows a warning once, tap "visit this website" to proceed.
"""
import http.server
import os
import ssl

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(PROJECT, "build", "web")
CERT = os.path.join(PROJECT, ".certs", "dev-cert.pem")
KEY = os.path.join(PROJECT, ".certs", "dev-key.pem")
PORT = 8443


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # iOS caches aggressively; always serve the freshest build.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


Handler.extensions_map[".wasm"] = "application/wasm"

httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(CERT, KEY)
httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
print(f"Serving {ROOT} at https://0.0.0.0:{PORT}", flush=True)
while True:
    try:
        httpd.serve_forever()
    except Exception as exc:  # a bad TLS probe must not kill the server
        print(f"serve loop error, continuing: {exc}", flush=True)
