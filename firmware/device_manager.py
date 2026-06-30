"""
device_manager.py - Device registry and per-device information.

Local system metrics come from psutil. Remote metrics are fetched by
running a small set of read-only commands over an authenticated SSH
session (uptime, free, df) — never arbitrary remote code execution from
user-supplied strings, and only against devices already marked approved.
"""

import time
import socket
import platform

import psutil
from rich.console import Console
from rich.table import Table

from . import db

console = Console()

# Fixed, read-only commands only. No user input is ever concatenated into
# a remote shell command — this whitelist is the full extent of what the
# controller will ever execute on a remote node via `device info`.
_REMOTE_INFO_COMMANDS = {
    "uptime": "uptime -p",
    "mem": "free -m | awk '/Mem:/ {printf \"%.0f\", $3/$2*100}'",
    "disk": "df -h / | awk 'NR==2 {print $5}'",
}


def local_snapshot():
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    try:
        temps = psutil.sensors_temperatures()
        temp = None
        for entries in temps.values():
            if entries:
                temp = entries[0].current
                break
    except Exception:
        temp = None
    return {
        "name": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu,
        "ram": mem,
        "storage": disk,
        "temp": temp,
    }


def register_device(name, ip=None, hostname=None, os_name=None, role="worker"):
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO devices (name, ip, hostname, os, role, approved, last_seen)
               VALUES (?, ?, ?, ?, ?, 0, ?)
               ON CONFLICT(name) DO UPDATE SET
                 ip=excluded.ip, hostname=excluded.hostname,
                 os=excluded.os, last_seen=excluded.last_seen""",
            (name, ip, hostname, os_name, role, time.time()),
        )
    db.log_event("INFO", "device_manager", f"Registered device '{name}' ({ip})")


def update_metrics(name, cpu=None, ram=None, storage=None):
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE devices SET cpu=?, ram=?, storage=?, last_seen=? WHERE name=?",
            (cpu, ram, storage, time.time(), name),
        )


def list_devices():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def get_device(name):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM devices WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def remove_device(name):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM devices WHERE name = ?", (name,))
        conn.execute("DELETE FROM tokens WHERE device_name = ?", (name,))
    db.log_event("INFO", "device_manager", f"Removed device '{name}'")


def show_devices_table():
    devices = list_devices()
    table = Table(title="Connected Devices")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("IP")
    table.add_column("Role")
    table.add_column("CPU")
    table.add_column("RAM")
    table.add_column("Storage")
    table.add_column("Status")

    if not devices:
        console.print("[yellow]No devices registered yet. Try 'cluster add <ip>' or 'devices scan'.[/yellow]")
        return

    now = time.time()
    for d in devices:
        online = d["last_seen"] and (now - d["last_seen"] < 120)
        status = "[green]Online[/green]" if online else "[red]Offline[/red]"
        if not d["approved"]:
            status = "[yellow]Pending approval[/yellow]"
        table.add_row(
            d["name"],
            d["ip"] or "-",
            d["role"] or "worker",
            f"{d['cpu']:.0f}%" if d["cpu"] is not None else "-",
            f"{d['ram']:.0f}%" if d["ram"] is not None else "-",
            f"{d['storage']:.0f}%" if d["storage"] is not None else "-",
            status,
        )
    console.print(table)


def fetch_remote_info_over_ssh(ip, username, key_path, timeout=5):
    """
    Read-only remote info via SSH using the fixed command whitelist above.
    Returns a dict, or None on failure. Requires paramiko and a reachable
    SSH host with the controller's key already authorized on that node
    (standard `ssh-copy-id` style trust, set up by the user ahead of time).
    """
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.load_system_host_keys()
        client.connect(ip, username=username, key_filename=key_path, timeout=timeout)

        results = {}
        for label, cmd in _REMOTE_INFO_COMMANDS.items():
            _, stdout, _ = client.exec_command(cmd, timeout=timeout)
            results[label] = stdout.read().decode().strip()
        client.close()
        return results
    except Exception as e:
        db.log_event("ERROR", "device_manager", f"SSH info fetch failed for {ip}: {e}")
        return None


def show_device_info(name):
    if name == socket.gethostname() or name in ("local", "self"):
        info = local_snapshot()
        table = Table(title=f"Device Info: {info['name']} (local)")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("IP", info["ip"])
        table.add_row("OS", info["os"])
        table.add_row("CPU", f"{info['cpu']:.1f}%")
        table.add_row("RAM", f"{info['ram']:.1f}%")
        table.add_row("Storage", f"{info['storage']:.1f}%")
        if info["temp"] is not None:
            table.add_row("Temperature", f"{info['temp']:.1f}°C")
        console.print(table)
        return

    device = get_device(name)
    if not device:
        console.print(f"[red]No device named '{name}' found. Try 'devices' to list known nodes.[/red]")
        return

    table = Table(title=f"Device Info: {device['name']}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("IP", device["ip"] or "-")
    table.add_row("Hostname", device["hostname"] or "-")
    table.add_row("OS", device["os"] or "unknown")
    table.add_row("Role", device["role"] or "worker")
    table.add_row("Approved", "Yes" if device["approved"] else "No (pending)")
    table.add_row("CPU", f"{device['cpu']:.0f}%" if device["cpu"] is not None else "-")
    table.add_row("RAM", f"{device['ram']:.0f}%" if device["ram"] is not None else "-")
    table.add_row("Storage", f"{device['storage']:.0f}%" if device["storage"] is not None else "-")
    if device["last_seen"]:
        ago = int(time.time() - device["last_seen"])
        table.add_row("Last seen", f"{ago}s ago")
    console.print(table)
