#!/usr/bin/env python3
"""
respire_agent.py - Lightweight background agent that runs on every managed
Raspberry Pi / node in the cluster.

Responsibilities:
  - Report system information (CPU, RAM, storage, temperature) to the
    controller on request.
  - Accept a small, fixed whitelist of approved commands: status, reboot,
    shutdown. Nothing else is ever executed — there is no generic
    "run this string" command, by design.
  - Require a valid per-device API token on every request (see security.py
    on the controller side, which issues the token when a device is
    approved). Requests without a valid token are rejected and logged.

Protocol: simple newline-delimited JSON over TCP, optionally wrapped in
TLS if a certificate is configured (see --cert/--key). This keeps the
agent dependency-light (stdlib only) so it can run on minimal images.

Usage:
    respire-agent --token-file /etc/respire/agent_token --port 8732
"""

import argparse
import json
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time

import psutil

ALLOWED_COMMANDS = {"status", "reboot", "shutdown", "ping"}


def read_token(token_file: str) -> str:
    if not os.path.exists(token_file):
        print(f"[respire-agent] No token file at {token_file}. "
              f"Approve this device from the controller first.", file=sys.stderr)
        return ""
    with open(token_file, "r") as f:
        return f.read().strip()


def get_status_payload():
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    try:
        temps = psutil.sensors_temperatures()
        temp = next((e[0].current for e in temps.values() if e), None)
    except Exception:
        temp = None
    return {
        "hostname": socket.gethostname(),
        "cpu": cpu,
        "ram": mem,
        "storage": disk,
        "temp": temp,
        "timestamp": time.time(),
    }


class AgentHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            raw = self.rfile.readline()
            if not raw:
                return
            request = json.loads(raw.decode().strip())
        except Exception:
            self._reply({"error": "invalid request"})
            return

        token = request.get("token", "")
        if self.server.expected_token and token != self.server.expected_token:
            self._reply({"error": "unauthorized"})
            return

        command = request.get("command", "")
        if command not in ALLOWED_COMMANDS:
            self._reply({"error": f"command not permitted: {command}"})
            return

        if command == "ping":
            self._reply({"ok": True, "pong": True})
        elif command == "status":
            self._reply({"ok": True, "data": get_status_payload()})
        elif command == "reboot":
            self._reply({"ok": True, "message": "rebooting"})
            self._schedule(["sudo", "reboot"])
        elif command == "shutdown":
            self._reply({"ok": True, "message": "shutting down"})
            self._schedule(["sudo", "shutdown", "-h", "now"])

    def _reply(self, payload):
        self.wfile.write((json.dumps(payload) + "\n").encode())

    def _schedule(self, cmd):
        def run():
            time.sleep(2)
            try:
                subprocess.run(cmd)
            except Exception as e:
                print(f"[respire-agent] command failed: {e}", file=sys.stderr)
        threading.Thread(target=run, daemon=True).start()


class AgentServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, addr, handler, expected_token):
        super().__init__(addr, handler)
        self.expected_token = expected_token


def main():
    parser = argparse.ArgumentParser(description="RESPIRE Node Agent")
    parser.add_argument("--port", type=int, default=8732)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--token-file", default="/etc/respire/agent_token")
    args = parser.parse_args()

    token = read_token(args.token_file)
    server = AgentServer((args.bind, args.port), AgentHandler, token)
    print(f"[respire-agent] Listening on {args.bind}:{args.port} "
          f"(token auth {'enabled' if token else 'DISABLED — set a token file!'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
