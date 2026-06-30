"""
config.py - Configuration loading, saving, and interactive config menu.
"""

import os
import yaml
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

console = Console()

CONFIG_DIR = os.path.expanduser("~/.respire")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")

DEFAULT_CONFIG = {
    "node_name": "raspberrypi-01",
    "cluster_name": "Main Lab",
    "role": "controller",
    "discovery": {
        "enabled": True,
        "subnet": "auto",
        "interval_seconds": 60,
    },
    "agent": {
        "port": 8732,
        "require_token": True,
    },
    "monitor": {
        "refresh_seconds": 2,
    },
    "ui": {
        "theme": "cyan",
        "show_banner": True,
    },
}


def ensure_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    return load_config()


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)


def show_config_menu():
    """Interactive configuration menu shown by the `config` command."""
    cfg = load_config()

    while True:
        table = Table(title="RESPIRE Configuration", show_lines=False)
        table.add_column("#", style="bold cyan", width=3)
        table.add_column("Setting")
        table.add_column("Value", style="green")

        table.add_row("1", "Node name", str(cfg["node_name"]))
        table.add_row("2", "Cluster name", str(cfg["cluster_name"]))
        table.add_row("3", "Role", str(cfg["role"]))
        table.add_row("4", "Discovery enabled", str(cfg["discovery"]["enabled"]))
        table.add_row("5", "Discovery subnet", str(cfg["discovery"]["subnet"]))
        table.add_row("6", "Agent port", str(cfg["agent"]["port"]))
        table.add_row("7", "Require agent token", str(cfg["agent"]["require_token"]))
        table.add_row("8", "Monitor refresh (s)", str(cfg["monitor"]["refresh_seconds"]))
        table.add_row("0", "Save and exit", "")

        console.print(table)
        choice = Prompt.ask("Select an option to edit", default="0")

        if choice == "1":
            cfg["node_name"] = Prompt.ask("New node name", default=cfg["node_name"])
        elif choice == "2":
            cfg["cluster_name"] = Prompt.ask("New cluster name", default=cfg["cluster_name"])
        elif choice == "3":
            cfg["role"] = Prompt.ask(
                "New role", choices=["controller", "worker", "storage"], default=cfg["role"]
            )
        elif choice == "4":
            cfg["discovery"]["enabled"] = Confirm.ask(
                "Enable discovery?", default=cfg["discovery"]["enabled"]
            )
        elif choice == "5":
            cfg["discovery"]["subnet"] = Prompt.ask(
                "Subnet (e.g. 192.168.1.0/24 or 'auto')", default=cfg["discovery"]["subnet"]
            )
        elif choice == "6":
            cfg["agent"]["port"] = int(Prompt.ask("Agent port", default=str(cfg["agent"]["port"])))
        elif choice == "7":
            cfg["agent"]["require_token"] = Confirm.ask(
                "Require token auth on agent?", default=cfg["agent"]["require_token"]
            )
        elif choice == "8":
            cfg["monitor"]["refresh_seconds"] = int(
                Prompt.ask("Monitor refresh seconds", default=str(cfg["monitor"]["refresh_seconds"]))
            )
        elif choice == "0":
            save_config(cfg)
            console.print("[bold green]Configuration saved.[/bold green]")
            break
        else:
            console.print("[red]Invalid option.[/red]")
