#!/usr/bin/env python3
"""
main.py - Entry point for RESPIRE homelab.

Run with:
    python3 main.py

Or, after installation:
    respire
"""

import os
import sys
import time

# Make sure the parent directory (the one containing the `firmware/` package)
# is on sys.path. This is required because running `python3 main.py`
# directly only adds this file's own directory (firmware/) to sys.path,
# not its parent — so `import firmware` would otherwise fail no matter
# where main.py is installed.
_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

from rich.console import Console

from firmware import config as config_mod
from firmware import db
from firmware import cli

console = Console()

BOOT_LINES = [
    "Loading services...",
    "Checking cluster...",
    "Starting interface...",
]


def show_boot_sequence():
    console.print("[bold cyan]RESPIRE OS[/bold cyan]\n")
    for line in BOOT_LINES:
        console.print(f"[dim]{line}[/dim]")
        time.sleep(0.4)
    console.print()


def main():
    db.init_db()
    cfg = config_mod.ensure_config()

    if "--no-boot-animation" not in sys.argv:
        show_boot_sequence()

    db.log_event("INFO", "main", "RESPIRE started.")
    cli.run_interactive(cfg)


if __name__ == "__main__":
    main()