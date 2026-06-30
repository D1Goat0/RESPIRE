# RESPIRE — Homelab Control System

A little side project that turns a Raspberry Pi into something that *feels*
like real network appliance firmware instead of just another Linux box you
SSH into. Boots straight into a dashboard, shows you what's online in your
lab, and lets you poke at everything from one terminal instead of juggling
ten SSH sessions.

Built by [L*UKE (D1Goat0)](https://github.com/D1Goat0) and
[D3CRYPT (D3CRYPT-1)](https://github.com/D3CRYPT-1) because we got tired of
`ssh pi@192.168.1.whatever` fifteen times a day and wanted our home lab to
look a little less like a pile of SD cards and a little more like something
out of a server room. Mostly a hobby project, scratch-your-own-itch energy.

```
------------------------------------------------
 RESPIRE
 Node: raspberrypi-01
 Status: ONLINE
 Cluster: Main Lab

 Connected Devices:
 [1] raspberrypi-02   CPU: 24%  RAM: 41%  Storage: 62%  Online
 [2] NAS-01            Storage: 4TB / 8TB             Online
 [3] worker-node       Docker: Running  Containers: 8
------------------------------------------------
```

## Why this exists

If you run a home lab you know the drill — a couple Pis, maybe a NAS, a
worker node running half your Docker containers, and you're constantly
hopping between terminals just to check if something's still alive. This
project wraps all of that into one console that boots up looking clean and
tells you what's going on at a glance, instead of staring at a blank shell
prompt wondering what you even named that third Pi.

It's not trying to be Kubernetes or anything fancy — just a lightweight
layer on top of plain Linux that makes managing a handful of boxes less
annoying.

## Project layout

```
respire-homelab/
├── firmware/
│   ├── main.py            # entry point + boot sequence
│   ├── cli.py              # interactive console, banner, command dispatch
│   ├── device_manager.py   # device registry + local/remote stats
│   ├── cluster.py          # node registration, roles, heartbeat
│   ├── network.py          # network info + ping-based discovery
│   ├── storage.py          # local drives + network share mounting
│   ├── monitor.py          # live terminal dashboard (rich.Live)
│   ├── security.py         # SSH keys, API tokens, device approval
│   ├── config.py           # YAML config + interactive config menu
│   └── db.py                # shared SQLite schema/helpers
├── agent/
│   └── respire_agent.py    # tiny per-node background service
├── systemd/
│   ├── respire.service        # boots the console on tty1
│   └── respire-agent.service  # runs the node agent
├── config/
│   └── example_config.yaml
├── requirements.txt
└── install.sh
```

## What you'll need

- Raspberry Pi OS Lite (Bookworm or newer) or basically any Debian-based box
- Python 3.9+
- Your devices reachable on the same network

Dependencies (installed for you by `install.sh`):
`rich`, `prompt_toolkit`, `psutil`, `paramiko`, `PyYAML`

## Quick start

```bash
git clone <this-repo> respire-homelab
cd respire-homelab
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 firmware/main.py
```

## Actually installing it on a Pi

```bash
sudo bash install.sh
```

What it does, roughly:
1. Pulls in OS deps (`python3`, `smartmontools`, `ssh`, etc.)
2. Drops the project into `/opt/respire`
3. Sets up its own virtualenv so it doesn't mess with your system Python
4. Adds the `respire` and `respire-agent` commands
5. Installs and enables the `respire-agent` service
6. Asks if you want it to take over the tty1 login screen on boot — say
   yes if you want the full "appliance" feel, say no if you'd rather just
   type `respire` whenever you feel like it

After that:

```bash
respire
```

## What boot looks like (if you opt in)

```
RESPIRE OS

Loading services...
Checking cluster...
Starting interface...
```

Then it drops you straight into the console. Linux is still right there
underneath — `exit` gets you a normal shell, and other TTYs / SSH still
work like always. We didn't want to lock anyone out of their own machine
for the sake of a vibe.

## Commands

| Command | What it does |
|---|---|
| `help` | Lists all commands |
| `devices` | Lists known devices (`devices scan` to find new ones) |
| `device info <name>` | Details on one device |
| `connect <name>` | SSH into another node |
| `cluster status` | Shows all cluster members |
| `cluster add <ip>` | Registers a node (goes into "pending" until approved) |
| `cluster remove <name>` | Drops a node from the cluster |
| `cluster role <name> <role>` | Sets a node's role: controller / worker / storage |
| `storage` | Local drives + capacity |
| `mount <share> <mountpoint>` | Mounts an NFS/Samba share |
| `network` | Interfaces, IP, throughput |
| `services` | Running systemd services |
| `logs` | Recent log entries |
| `update` | Pulls latest code + bumps dependencies |
| `reboot [name]` | Reboots local node, or a named approved node |
| `shutdown [name]` | Shuts down local node, or a named approved node |
| `monitor` | Live dashboard — CPU/RAM/disk/net/cluster, refreshes every couple seconds |
| `docker [ps\|start\|stop\|restart] <name>` | Basic container management |
| `security` | Auth status, approvals, token counts |
| `config` | Interactive settings menu |
| `exit` / `quit` | Back to a normal shell |

Tab-completion and command history (`~/.respire/history`) work like you'd
expect, courtesy of `prompt_toolkit`.

## How discovery works (and what it doesn't do)

`devices scan` / `network` does a plain ping sweep of your local `/24` —
basically the same thing your router's "connected devices" page does — and
resolves hostnames for whatever answers. That's it. No port scanning, no
poking at services, no credential guessing, nothing offensive. A device
only becomes "managed" once you explicitly run `cluster add <ip>` and
approve it.

We were pretty deliberate about keeping this a *management* tool and not
accidentally building a recon tool. It's for your own gear.

## Security bits

- **Nothing happens until you approve it.** New nodes sit in "pending"
  until you say so — either right when you add them or later via
  `device info <name>`.
- **Per-device tokens.** Approving a device hands it a random 256-bit
  token used to authenticate agent traffic.
- **SSH keys, not passwords.** `connect` uses a dedicated key
  (auto-generated at `~/.ssh/respire_id_ed25519` if you don't have one).
- **The agent only knows four commands.** `status`, `ping`, `reboot`,
  `shutdown` — full stop. There's no "run arbitrary string" path on
  purpose, even though that would've been less code to write.

## The node agent

Runs on every Pi/server you want to manage remotely. Installed
automatically alongside the console:

```bash
sudo bash install.sh
systemctl status respire-agent
```

Listens on TCP `8732` by default, speaks tiny JSON-over-socket, and just
ignores anything without the right token.

## Storage

`storage` shows what's mounted locally — capacity, usage, SMART temps if
`smartmontools` is around. `mount` is a thin wrapper over the normal
`mount` command for NFS/Samba shares; it'll make the mountpoint directory
for you if it doesn't exist yet.

## Live monitoring

`monitor` opens a live-refreshing view (interval is configurable) showing
your local CPU/RAM/disk/temp/network plus whatever stats your other nodes
have last reported in.

## Config

Lives at `~/.respire/config.yaml`, gets created on first run from
`config/example_config.yaml`. Edit it through the `config` command or just
open the file:

```yaml
node_name: raspberrypi-01
cluster_name: Main Lab
role: controller
discovery:
  enabled: true
  subnet: auto
agent:
  port: 8732
  require_token: true
monitor:
  refresh_seconds: 2
```

## Stuff we might add later

Kept the code modular on purpose so these don't require a rewrite:
- Web dashboard
- Mobile app
- Kubernetes / Docker Swarm support
- Scheduled backups
- Some kind of AI assistant for monitoring/alerts
- Hardware health alerts
- Cluster-wide remote updates

No promises on timeline, this is a "when we feel like it" project.

## Uninstalling

```bash
sudo systemctl disable --now respire.service respire-agent.service
sudo rm -f /etc/systemd/system/respire.service /etc/systemd/system/respire-agent.service
sudo rm -f /usr/local/bin/respire /usr/local/bin/respire-agent
sudo rm -rf /opt/respire /etc/respire
rm -rf ~/.respire
sudo systemctl daemon-reload
```

## Credits

Built and maintained by [L*UKE](https://github.com/D1Goat0) and
[D3CRYPT](https://github.com/D3CRYPT-1) for our own home lab, mostly
because we wanted a cleaner workflow and an excuse to mess around with
`rich` and `prompt_toolkit`. Use it, fork it, rip pieces out of it for your
own setup — that's basically why we made it public.
