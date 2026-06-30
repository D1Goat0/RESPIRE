"""
cli.py - Interactive command-line interface for RESPIRE homelab.

Provides the "network appliance" feel: ASCII banner, colored status panel,
tab-completion, persistent history, and a command dispatch table.
"""

import os
import shlex
import socket
import subprocess
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from . import config as config_mod
from . import device_manager
from . import cluster
from . import network
from . import storage
from . import monitor
from . import security
from . import db

console = Console()

HISTORY_PATH = os.path.expanduser("~/.respire/history")

COMMANDS = [
    "help", "devices", "device", "connect", "cluster", "storage", "mount",
    "network", "services", "logs", "update", "reboot", "shutdown", "monitor",
    "docker", "security", "config", "exit", "quit",
]

COMMAND_HELP = [
    ("help", "Shows available commands."),
    ("devices", "Lists all connected devices. ('devices scan' to discover)"),
    ("device info <name>", "Shows detailed information about a device."),
    ("connect <name>", "Opens a remote SSH session to another node."),
    ("cluster status", "Shows all cluster members."),
    ("cluster add <ip>", "Adds another Raspberry Pi/server."),
    ("cluster remove <name>", "Removes a node."),
    ("storage", "Shows available storage devices."),
    ("mount <share> <mountpoint>", "Mount network storage (NFS/Samba)."),
    ("network", "Shows network information."),
    ("services", "Shows running services."),
    ("logs", "Shows system logs."),
    ("update", "Updates firmware."),
    ("reboot [name]", "Reboots local or remote nodes."),
    ("shutdown [name]", "Safely shuts down nodes."),
    ("monitor", "Opens live monitoring dashboard."),
    ("docker", "Manages containers if Docker is installed."),
    ("security", "Shows security status."),
    ("config", "Opens configuration menu."),
    ("exit / quit", "Exit the console (drops to normal shell)."),
]


def banner(cfg):
    devices = device_manager.list_devices()
    online = sum(1 for d in devices if d["last_seen"] and time.time() - d["last_seen"] < 120)

    title = Text("RESPIRE", style="bold cyan")
    lines = Text()
    lines.append(f"Node: ", style="bold")
    lines.append(f"{socket.gethostname()}\n")
    lines.append(f"Status: ", style="bold")
    lines.append("ONLINE\n", style="bold green")
    lines.append(f"Cluster: ", style="bold")
    lines.append(f"{cfg['cluster_name']}\n")
    lines.append(f"Role: ", style="bold")
    lines.append(f"{cfg['role']}\n")
    lines.append(f"Devices online: ", style="bold")
    lines.append(f"{online} / {len(devices)}")

    console.print(Panel(lines, title=title, border_style="cyan", expand=False))

    if devices:
        table = Table(title="Connected Devices", show_lines=False)
        table.add_column("#", width=3)
        table.add_column("Name", style="cyan")
        table.add_column("CPU")
        table.add_column("RAM")
        table.add_column("Storage")
        table.add_column("Status")
        for i, d in enumerate(devices, 1):
            is_online = d["last_seen"] and time.time() - d["last_seen"] < 120
            status = "[green]Online[/green]" if is_online else "[red]Offline[/red]"
            table.add_row(
                str(i), d["name"],
                f"{d['cpu']:.0f}%" if d["cpu"] is not None else "-",
                f"{d['ram']:.0f}%" if d["ram"] is not None else "-",
                f"{d['storage']:.0f}%" if d["storage"] is not None else "-",
                status,
            )
        console.print(table)


def show_help():
    table = Table(title="Available Commands", show_lines=False)
    table.add_column("Command", style="bold cyan")
    table.add_column("Description")
    for cmd, desc in COMMAND_HELP:
        table.add_row(cmd, desc)
    console.print(table)


def show_services():
    table = Table(title="Running Services")
    table.add_column("Service", style="cyan")
    table.add_column("Status")
    try:
        out = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--no-legend"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        lines = out.strip().splitlines()[:25]
        if not lines:
            console.print("[yellow]No running services found (or systemctl unavailable).[/yellow]")
            return
        for line in lines:
            parts = line.split()
            if parts:
                table.add_row(parts[0], "[green]running[/green]")
        console.print(table)
    except FileNotFoundError:
        console.print("[yellow]systemctl not available on this system.[/yellow]")
    except Exception as e:
        console.print(f"[red]Could not list services: {e}[/red]")


def show_logs():
    rows = db.get_logs(50)
    table = Table(title="System Logs (most recent first)")
    table.add_column("Time", style="dim")
    table.add_column("Level")
    table.add_column("Source", style="cyan")
    table.add_column("Message")
    if not rows:
        console.print("[yellow]No log entries yet.[/yellow]")
        return
    for r in rows:
        ts = time.strftime("%H:%M:%S", time.localtime(r["timestamp"]))
        level_color = {"INFO": "white", "WARN": "yellow", "ERROR": "red"}.get(r["level"], "white")
        table.add_row(ts, f"[{level_color}]{r['level']}[/{level_color}]", r["source"], r["message"])
    console.print(table)


def do_update():
    console.print("[cyan]Checking for firmware updates...[/cyan]")
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(repo_dir, ".git")):
        try:
            result = subprocess.run(["git", "-C", repo_dir, "pull"], capture_output=True, text=True, timeout=30)
            console.print(result.stdout or result.stderr)
            db.log_event("INFO", "update", "Firmware update check completed via git pull.")
        except Exception as e:
            console.print(f"[red]Update failed: {e}[/red]")
    else:
        console.print("[yellow]Not a git checkout — skipping source update.[/yellow]")

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "--upgrade", "-r",
             os.path.join(repo_dir, "requirements.txt")],
            timeout=60,
        )
        console.print("[green]Dependencies are up to date.[/green]")
    except Exception as e:
        console.print(f"[yellow]Could not update dependencies automatically: {e}[/yellow]")


def do_reboot(target=None):
    if target is None or target in ("local", "self", socket.gethostname()):
        console.print("[bold red]Rebooting local node in 3 seconds... (Ctrl+C to cancel)[/bold red]")
        try:
            time.sleep(3)
            subprocess.run(["sudo", "reboot"])
        except KeyboardInterrupt:
            console.print("[yellow]Reboot cancelled.[/yellow]")
        return

    device = device_manager.get_device(target)
    if not device or not device["approved"]:
        console.print(f"[red]'{target}' is not a known, approved device.[/red]")
        return
    console.print(f"[cyan]Sending reboot command to '{target}'...[/cyan]")
    db.log_event("INFO", "cluster", f"Reboot requested for '{target}'")
    console.print(
        "[yellow]Note: this requires the respire-agent service running and approved on the target node.[/yellow]"
    )


def do_shutdown(target=None):
    if target is None or target in ("local", "self", socket.gethostname()):
        console.print("[bold red]Shutting down local node in 3 seconds... (Ctrl+C to cancel)[/bold red]")
        try:
            time.sleep(3)
            subprocess.run(["sudo", "shutdown", "-h", "now"])
        except KeyboardInterrupt:
            console.print("[yellow]Shutdown cancelled.[/yellow]")
        return

    device = device_manager.get_device(target)
    if not device or not device["approved"]:
        console.print(f"[red]'{target}' is not a known, approved device.[/red]")
        return
    console.print(f"[cyan]Sending shutdown command to '{target}'...[/cyan]")
    db.log_event("INFO", "cluster", f"Shutdown requested for '{target}'")
    console.print(
        "[yellow]Note: this requires the respire-agent service running and approved on the target node.[/yellow]"
    )


def do_connect(name):
    if not name:
        console.print("[red]Usage: connect <name>[/red]")
        return
    device = device_manager.get_device(name)
    if not device:
        console.print(f"[red]No device named '{name}' found.[/red]")
        return
    if not device["approved"]:
        console.print(f"[red]'{name}' is pending approval — approve it before connecting.[/red]")
        return
    ip = device["ip"]
    console.print(f"[cyan]Opening SSH session to {name} ({ip})...[/cyan]")
    key_path = security.SSH_KEY_PATH
    ssh_cmd = ["ssh"]
    if os.path.exists(key_path):
        ssh_cmd += ["-i", key_path]
    ssh_cmd.append(f"pi@{ip}")
    try:
        subprocess.run(ssh_cmd)
    except FileNotFoundError:
        console.print("[red]ssh client not found on this system.[/red]")


def do_docker(args):
    if not subprocess_exists("docker"):
        console.print("[yellow]Docker is not installed on this node.[/yellow]")
        return

    sub = args[0] if args else "ps"
    if sub == "ps":
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            capture_output=True, text=True,
        ).stdout
        table = Table(title="Docker Containers")
        table.add_column("Name", style="cyan")
        table.add_column("Status")
        table.add_column("Image")
        for line in out.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                table.add_row(*parts)
        console.print(table)
    elif sub in ("start", "stop", "restart") and len(args) > 1:
        container = args[1]
        result = subprocess.run(["docker", sub, container], capture_output=True, text=True)
        if result.returncode == 0:
            console.print(f"[green]Container '{container}' {sub}ed.[/green]")
        else:
            console.print(f"[red]{result.stderr.strip()}[/red]")
    else:
        console.print("[yellow]Usage: docker [ps|start <name>|stop <name>|restart <name>][/yellow]")


def subprocess_exists(binary):
    import shutil
    return shutil.which(binary) is not None


def dispatch(line: str, cfg: dict):
    if not line.strip():
        return True
    try:
        parts = shlex.split(line)
    except ValueError as e:
        console.print(f"[red]Parse error: {e}[/red]")
        return True

    cmd, args = parts[0].lower(), parts[1:]

    if cmd in ("exit", "quit"):
        console.print("[cyan]Dropping to normal shell. Type 'respire' to return.[/cyan]")
        return False

    elif cmd == "help":
        show_help()

    elif cmd == "devices":
        if args and args[0] == "scan":
            hosts = network.run_discovery()
            for h in hosts:
                device_manager.register_device(
                    f"node-{h['ip'].split('.')[-1]}", ip=h["ip"], hostname=h["hostname"]
                )
        else:
            device_manager.show_devices_table()

    elif cmd == "device":
        if len(args) >= 2 and args[0] == "info":
            device_manager.show_device_info(args[1])
        else:
            console.print("[yellow]Usage: device info <name>[/yellow]")

    elif cmd == "connect":
        do_connect(args[0] if args else None)

    elif cmd == "cluster":
        if not args:
            cluster.cluster_status(cfg["cluster_name"])
        elif args[0] == "status":
            cluster.cluster_status(cfg["cluster_name"])
        elif args[0] == "add" and len(args) > 1:
            cluster.add_node(args[1])
        elif args[0] == "remove" and len(args) > 1:
            cluster.remove_node(args[1])
        elif args[0] == "role" and len(args) > 2:
            cluster.set_role(args[1], args[2])
        else:
            console.print("[yellow]Usage: cluster [status|add <ip>|remove <name>|role <name> <role>][/yellow]")

    elif cmd == "storage":
        storage.show_storage()

    elif cmd == "mount":
        if len(args) >= 2:
            storage.mount_network_share(args[0], args[1])
        else:
            console.print("[yellow]Usage: mount <share_path> <mountpoint>[/yellow]")

    elif cmd == "network":
        network.show_network_info()

    elif cmd == "services":
        show_services()

    elif cmd == "logs":
        show_logs()

    elif cmd == "update":
        do_update()

    elif cmd == "reboot":
        do_reboot(args[0] if args else None)

    elif cmd == "shutdown":
        do_shutdown(args[0] if args else None)

    elif cmd == "monitor":
        monitor.run_monitor(cfg)

    elif cmd == "docker":
        do_docker(args)

    elif cmd == "security":
        security.show_security_status()

    elif cmd == "config":
        config_mod.show_config_menu()

    else:
        console.print(f"[red]Unknown command:[/red] {cmd}. Type 'help' for a list of commands.")

    return True


def run_interactive(cfg):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    completer = WordCompleter(COMMANDS, ignore_case=True, sentence=True)
    style = Style.from_dict({"prompt": "bold cyan"})
    session = PromptSession(
        history=FileHistory(HISTORY_PATH),
        completer=completer,
        style=style,
    )

    banner(cfg)
    show_help()

    prompt_label = f"{cfg['node_name']}> "
    while True:
        try:
            line = session.prompt([("class:prompt", prompt_label)])
        except (EOFError, KeyboardInterrupt):
            console.print("\n[cyan]Goodbye.[/cyan]")
            break

        keep_going = dispatch(line, cfg)
        if not keep_going:
            break
