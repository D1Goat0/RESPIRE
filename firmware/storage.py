"""
storage.py - Storage device inventory: local disks, USB/SSD, and network shares.
"""

import shutil
import subprocess

import psutil
from rich.console import Console
from rich.table import Table

console = Console()


def list_local_drives():
    drives = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, FileNotFoundError, OSError):
            continue
        drives.append({
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "percent": usage.percent,
        })
    return drives


def get_drive_temperature(device: str):
    """Best-effort temperature via smartctl, if installed. Returns None if unavailable."""
    if not shutil.which("smartctl"):
        return None
    try:
        out = subprocess.run(
            ["smartctl", "-A", device], capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            if "Temperature_Celsius" in line or "Airflow_Temperature" in line:
                parts = line.split()
                return parts[9] if len(parts) > 9 else None
    except Exception:
        return None
    return None


def show_storage():
    drives = list_local_drives()
    table = Table(title="Storage Devices")
    table.add_column("Device", style="cyan")
    table.add_column("Mount")
    table.add_column("FS")
    table.add_column("Capacity")
    table.add_column("Used")
    table.add_column("Health")

    if not drives:
        console.print("[yellow]No accessible local drives found.[/yellow]")
        return

    for d in drives:
        health = "[green]Good[/green]" if d["percent"] < 90 else "[red]Low space[/red]"
        table.add_row(
            d["device"],
            d["mountpoint"],
            d["fstype"],
            f"{d['total_gb']} GB",
            f"{d['used_gb']} GB ({d['percent']}%)",
            health,
        )
    console.print(table)
    console.print(
        "[dim]Network shares (Samba/NFS) appear here once mounted — use 'mount' to attach one.[/dim]"
    )


def mount_network_share(share_path: str, mountpoint: str, share_type: str = "nfs", options: str = ""):
    """
    Mount a network share. share_type is 'nfs' or 'cifs' (Samba).
    This wraps the standard `mount` utility; it does not invent new
    protocol handling and requires the mountpoint to already exist.
    """
    import os
    if not os.path.isdir(mountpoint):
        os.makedirs(mountpoint, exist_ok=True)

    cmd = ["sudo", "mount", "-t", share_type, share_path, mountpoint]
    if options:
        cmd = ["sudo", "mount", "-t", share_type, "-o", options, share_path, mountpoint]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            console.print(f"[green]Mounted {share_path} -> {mountpoint}[/green]")
            return True
        else:
            console.print(f"[red]Mount failed: {result.stderr.strip()}[/red]")
            return False
    except Exception as e:
        console.print(f"[red]Mount error: {e}[/red]")
        return False
