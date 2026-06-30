"""
monitor.py - Live terminal monitoring dashboard.
"""

import time
import socket

import psutil
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.progress_bar import ProgressBar

from . import device_manager

console = Console()


def _bar(percent, width=24):
    pb = ProgressBar(total=100, completed=percent, width=width)
    return pb


def _build_dashboard(cfg):
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    try:
        temps = psutil.sensors_temperatures()
        temp = next((e[0].current for e in temps.values() if e), None)
    except Exception:
        temp = None

    header = Table.grid(expand=True)
    header.add_column(justify="left")
    header.add_column(justify="right")
    header.add_row(
        f"[bold cyan]RESPIRE LIVE MONITOR[/bold cyan]  —  Node: {socket.gethostname()}",
        time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    local_table = Table(title="This Node", show_header=False, box=None)
    local_table.add_column("Metric", style="cyan", width=14)
    local_table.add_column("Value")
    local_table.add_row("CPU", f"{cpu:5.1f}%")
    local_table.add_row("RAM", f"{mem.percent:5.1f}%")
    local_table.add_row("Disk", f"{disk.percent:5.1f}%")
    if temp is not None:
        local_table.add_row("Temp", f"{temp:5.1f}°C")
    local_table.add_row("Net sent", f"{net.bytes_sent // (1024*1024)} MB")
    local_table.add_row("Net recv", f"{net.bytes_recv // (1024*1024)} MB")

    devices = device_manager.list_devices()
    cluster_table = Table(title="Cluster Devices")
    cluster_table.add_column("Name", style="cyan")
    cluster_table.add_column("CPU")
    cluster_table.add_column("RAM")
    cluster_table.add_column("Storage")
    cluster_table.add_column("Status")

    now = time.time()
    online_count = 1  # local node
    for d in devices:
        online = d["last_seen"] and (now - d["last_seen"] < 120)
        if online:
            online_count += 1
        status = "[green]●[/green] Online" if online else "[red]●[/red] Offline"
        cluster_table.add_row(
            d["name"],
            f"{d['cpu']:.0f}%" if d["cpu"] is not None else "-",
            f"{d['ram']:.0f}%" if d["ram"] is not None else "-",
            f"{d['storage']:.0f}%" if d["storage"] is not None else "-",
            status,
        )

    footer = f"[dim]{online_count} device(s) online   •   refresh every {cfg['monitor']['refresh_seconds']}s   •   Ctrl+C to exit[/dim]"

    body = Table.grid(expand=True)
    body.add_column(ratio=1)
    body.add_column(ratio=2)
    body.add_row(local_table, cluster_table)

    return Group(header, Panel(body, border_style="cyan"), footer)


def run_monitor(cfg):
    refresh = cfg.get("monitor", {}).get("refresh_seconds", 2)
    console.print("[cyan]Starting live monitor... press Ctrl+C to exit.[/cyan]")
    try:
        with Live(_build_dashboard(cfg), refresh_per_second=1, screen=False) as live:
            while True:
                time.sleep(refresh)
                live.update(_build_dashboard(cfg))
    except KeyboardInterrupt:
        console.print("\n[green]Exited live monitor.[/green]")
