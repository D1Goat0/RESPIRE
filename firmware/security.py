"""
security.py - Authentication, token management, and device approval.

Design principles:
  - Nodes must be explicitly approved before they can receive commands.
  - Agent-to-controller communication is authenticated with per-device
    API tokens (random, stored hashed-at-rest is recommended for production;
    this reference implementation stores them in the local sqlite DB which
    is itself only readable by the owning user).
  - SSH key-based auth is preferred over passwords for `connect`.
  - This module intentionally contains no scanning, exploitation, or
    credential-guessing logic of any kind.
"""

import secrets
import time
import os
import stat
from rich.console import Console
from rich.table import Table
from . import db

console = Console()
SSH_KEY_PATH = os.path.expanduser("~/.ssh/respire_id_ed25519")

def generate_token(device_name: str) -> str:
    token = secrets.token_hex(32)
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tokens (device_name, token, created_at) VALUES (?, ?, ?)",
            (device_name, token, time.time()),
        )
    return token

def get_token(device_name: str):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT token FROM tokens WHERE device_name = ?", (device_name,)
        ).fetchone()
        return row["token"] if row else None


def verify_token(device_name: str, token: str) -> bool:
    expected = get_token(device_name)
    return expected is not None and secrets.compare_digest(expected, token)


def approve_device(name: str):
    with db.get_conn() as conn:
        conn.execute("UPDATE devices SET approved = 1 WHERE name = ?", (name,))
    generate_token(name)
    db.log_event("INFO", "security", f"Device '{name}' approved and issued an API token.")


def revoke_device(name: str):
    with db.get_conn() as conn:
        conn.execute("UPDATE devices SET approved = 0 WHERE name = ?", (name,))
        conn.execute("DELETE FROM tokens WHERE device_name = ?", (name,))
    db.log_event("WARN", "security", f"Device '{name}' access revoked.")


def ensure_ssh_key():
    """Generate a local ed25519 keypair for controller->node SSH if one doesn't exist."""
    if os.path.exists(SSH_KEY_PATH):
        return SSH_KEY_PATH
    try:
        import paramiko
        key = paramiko.Ed25519Key.generate()
        key.write_private_key_file(SSH_KEY_PATH)
        os.chmod(SSH_KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)
        pub_path = SSH_KEY_PATH + ".pub"
        with open(pub_path, "w") as f:
            f.write(f"ssh-ed25519 {key.get_base64()} respire-controller\n")
        db.log_event("INFO", "security", "Generated new SSH keypair for cluster authentication.")
        return SSH_KEY_PATH
    except Exception as e:
        db.log_event("ERROR", "security", f"Failed to generate SSH key: {e}")
        return None


def show_security_status():
    table = Table(title="Security Status")
    table.add_column("Item", style="cyan")
    table.add_column("Status")

    ssh_ok = os.path.exists(SSH_KEY_PATH)
    table.add_row("SSH key authentication", "[green]Configured[/green]" if ssh_ok else "[yellow]Not configured[/yellow]")

    with db.get_conn() as conn:
        approved = conn.execute("SELECT COUNT(*) c FROM devices WHERE approved = 1").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) c FROM devices WHERE approved = 0").fetchone()["c"]
        tokens = conn.execute("SELECT COUNT(*) c FROM tokens").fetchone()["c"]

    table.add_row("Approved devices", str(approved))
    table.add_row("Pending approval", str(pending) if pending else "0")
    table.add_row("Active API tokens", str(tokens))
    table.add_row("Encrypted transport", "[green]SSH / TLS-wrapped agent[/green]")

    console.print(table)

    if pending:
        console.print(
            f"[yellow]{pending} device(s) awaiting approval.[/yellow] "
            f"Use 'cluster add <ip>' then approve via 'device info <name>'."
        )
