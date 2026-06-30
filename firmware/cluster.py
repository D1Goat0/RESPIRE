"""
cluster.py - Cluster membership, roles, and heartbeat tracking.
"""

import time
import socket

from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from . import db
from . import device_manager
from . import security
from . import network

console = Console()

VALID_ROLES = ("controller", "worker", "storage")


def cluster_status(cluster_name="Main Lab"):
    devices = device_manager.list_devices()
    table = Table(title=f"Cluster Status: {cluster_name}")
    table.add_column("Node", style="cyan")
    table.add_column("Role")
    table.add_column("IP")
    table.add_column("Status")
    table.add_column("Last Heartbeat")

    table.add_row(socket.gethostname(), "controller (this node)", "127.0.0.1", "[green]Online[/green]", "now")

    now = time.time()
    for d in devices:
        online = d["last_seen"] and (now - d["last_seen"] < 120)
        status = "[green]Online[/green]" if online else "[red]Offline[/red]"
        last_seen = f"{int(now - d['last_seen'])}s ago" if d["last_seen"] else "never"
        table.add_row(d["name"], d["role"] or "worker", d["ip"] or "-", status, last_seen)

    console.print(table)


def add_node(ip: str):
    """
    Register a node found at the given IP. The node is added in a
    'pending approval' state — it cannot receive any commands until
    explicitly approved, keeping with the explicit-consent security model.
    """
    hostname = "unknown"
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except Exception:
        pass

    name = hostname.split(".")[0] if hostname != "unknown" else f"node-{ip.split('.')[-1]}"
    device_manager.register_device(name, ip=ip, hostname=hostname, role="worker")
    console.print(f"[green]Node '{name}' ({ip}) added in pending state.[/green]")

    if Confirm.ask(f"Approve and trust '{name}' now?", default=True):
        security.approve_device(name)
        console.print(f"[bold green]'{name}' approved.[/bold green] An API token has been issued.")
    else:
        console.print(f"[yellow]'{name}' left pending. Approve later from 'device info {name}'.[/yellow]")

    return name


def remove_node(name: str):
    device = device_manager.get_device(name)
    if not device:
        console.print(f"[red]No such node: {name}[/red]")
        return
    device_manager.remove_device(name)
    console.print(f"[green]Node '{name}' removed from cluster.[/green]")


def set_role(name: str, role: str):
    if role not in VALID_ROLES:
        console.print(f"[red]Invalid role. Choose from: {', '.join(VALID_ROLES)}[/red]")
        return
    with db.get_conn() as conn:
        conn.execute("UPDATE devices SET role = ? WHERE name = ?", (role, name))
    console.print(f"[green]Role for '{name}' set to '{role}'.[/green]")


def record_heartbeat(name: str, status: str = "online"):
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO heartbeats (device_name, timestamp, status) VALUES (?, ?, ?)",
            (name, time.time(), status),
        )
        conn.execute("UPDATE devices SET last_seen = ? WHERE name = ?", (time.time(), name))
