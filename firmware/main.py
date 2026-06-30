#!/usr/bin/env python3
"""
main.py - Entry point for RESPIRE homelab.

Run with:
    python3 main.py

Or, after installation:
    respire
"""

import sys
import time

from rich.console import Console

try:
    from firmware import config as config_mod
    from firmware import db
    from firmware import cli
except ImportError:
    # Allow running directly from inside the firmware/ directory too.
    import config as config_mod
    import db
    import cli

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
