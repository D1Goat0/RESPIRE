"""
network.py - Network information and local device discovery.

Discovery is intentionally limited to benign, standard inventory checks:
  - ICMP ping sweep of the local /24 subnet (the same thing `nmap -sn` or
    a router's "connected devices" page does)
  - Reverse DNS / hostname lookup
  - A connection check against the respire-agent port (if the optional
    agent is running and the device has been approved)

There is no port scanning beyond the single agent port, no credential
brute-forcing, and no exploitation of any kind. Devices must be
explicitly approved (see security.py) before any command can be sent
to them.
"""

import ipaddress
import socket
import subprocess
import platform
import concurrent.futures
import psutil

from rich.console import Console
from rich.table import Table

console = Console()


def get_local_subnet():
    """Best-effort detection of the local IPv4 /24 the active interface is on."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        network = ipaddress.ip_network(local_ip + "/24", strict=False)
        return str(network), local_ip
    except Exception:
        return "192.168.1.0/24", "127.0.0.1"


def _ping(host: str, timeout_s: float = 0.5) -> bool:
    """Single ICMP ping, OS-aware, used only for liveness — not a scan/exploit tool."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    timeout_flag = "-w" if platform.system().lower() == "windows" else "-W"
    timeout_val = str(int(timeout_s * 1000)) if platform.system().lower() == "windows" else str(int(timeout_s) or 1)
    cmd = ["ping", param, "1", timeout_flag, timeout_val, host]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_s + 1
        )
        return result.returncode == 0
    except Exception:
        return False


def _resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyname_ex(ip)[0]
    except Exception:
        return "unknown"


def scan_local_network(subnet: str = None, max_workers: int = 64):
    """
    Ping-sweep the subnet and return a list of live hosts with hostname info.
    This is a discovery convenience for inventory only; it does not probe
    services, ports, or attempt authentication of any kind.
    """
    if subnet is None or subnet == "auto":
        subnet, _ = get_local_subnet()

    network = ipaddress.ip_network(subnet, strict=False)
    hosts = [str(h) for h in network.hosts()]

    live_hosts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_host = {pool.submit(_ping, h): h for h in hosts}
        for future in concurrent.futures.as_completed(future_to_host):
            host = future_to_host[future]
            try:
                if future.result():
                    live_hosts.append(host)
            except Exception:
                pass

    results = []
    for ip in sorted(live_hosts, key=lambda x: ipaddress.ip_address(x)):
        results.append({
            "ip": ip,
            "hostname": _resolve_hostname(ip),
        })
    return results


def show_network_info():
    subnet, local_ip = get_local_subnet()
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io_counters = psutil.net_io_counters()

    table = Table(title="Network Information")
    table.add_column("Interface", style="cyan")
    table.add_column("Address")
    table.add_column("Status")
    table.add_column("Speed")

    for iface, addr_list in addrs.items():
        ipv4 = next((a.address for a in addr_list if a.family == socket.AF_INET), None)
        if not ipv4:
            continue
        st = stats.get(iface)
        status = "UP" if st and st.isup else "DOWN"
        speed = f"{st.speed}Mbps" if st and st.speed > 0 else "n/a"
        table.add_row(iface, ipv4, status, speed)

    console.print(table)
    console.print(f"[bold]Local subnet:[/bold] {subnet}    [bold]Local IP:[/bold] {local_ip}")
    console.print(
        f"[bold]Total sent:[/bold] {io_counters.bytes_sent // 1024 // 1024} MB   "
        f"[bold]Total received:[/bold] {io_counters.bytes_recv // 1024 // 1024} MB"
    )


def run_discovery(subnet: str = None):
    console.print("[cyan]Scanning local network for devices...[/cyan]")
    hosts = scan_local_network(subnet)
    table = Table(title="Discovered Hosts")
    table.add_column("IP Address", style="cyan")
    table.add_column("Hostname")
    for h in hosts:
        table.add_row(h["ip"], h["hostname"])
    console.print(table)
    console.print(f"[green]{len(hosts)} host(s) responded.[/green] "
                  f"Use 'cluster add <ip>' to register and approve a node.")
    return hosts
