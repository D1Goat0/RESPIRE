#!/usr/bin/env bash
#
# install.sh - Installs RESPIRE on Raspberry Pi OS Lite
# (or any Debian-based Linux board).
#
# Usage:
#   sudo bash install.sh
#
set -euo pipefail

INSTALL_DIR="/opt/respire"
SERVICE_DIR="/etc/systemd/system"
CONFIG_DIR="/etc/respire"
REPO_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash install.sh"
  exit 1
fi

echo "=== RESPIRE Installer ==="

echo "[1/7] Installing system dependencies..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git smartmontools ssh

echo "[2/7] Creating install directory at ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
cp -r "${REPO_SRC_DIR}/firmware" "${INSTALL_DIR}/"
cp -r "${REPO_SRC_DIR}/agent" "${INSTALL_DIR}/"
cp "${REPO_SRC_DIR}/requirements.txt" "${INSTALL_DIR}/"

echo "[3/7] Setting up Python virtual environment..."
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip -q
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" -q

echo "[4/7] Creating config and agent token directories..."
mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_DIR}/agent_token" ]]; then
  echo "(no token yet — generated on first approval from the controller)" > "${CONFIG_DIR}/agent_token.example"
fi

echo "[5/7] Installing the 'respire' launcher command..."
cat > /usr/local/bin/respire <<EOF
#!/usr/bin/env bash
exec ${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/firmware/main.py "\$@"
EOF
chmod +x /usr/local/bin/respire

cat > /usr/local/bin/respire-agent <<EOF
#!/usr/bin/env bash
exec ${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/agent/respire_agent.py "\$@"
EOF
chmod +x /usr/local/bin/respire-agent

echo "[6/7] Installing systemd services..."
cp "${REPO_SRC_DIR}/systemd/respire-agent.service" "${SERVICE_DIR}/"
sed -i "s#/usr/bin/python3#${INSTALL_DIR}/venv/bin/python3#" "${SERVICE_DIR}/respire-agent.service"
systemctl daemon-reload
systemctl enable respire-agent.service
systemctl restart respire-agent.service

read -r -p "Replace the login prompt on tty1 with the RESPIRE console on boot? [y/N] " REPLACE_TTY
if [[ "${REPLACE_TTY,,}" == "y" ]]; then
  cp "${REPO_SRC_DIR}/systemd/respire.service" "${SERVICE_DIR}/"
  sed -i "s#/usr/bin/python3#${INSTALL_DIR}/venv/bin/python3#" "${SERVICE_DIR}/respire.service"
  systemctl daemon-reload
  systemctl enable respire.service
  echo "respire.service enabled — it will take over tty1 on next boot."
  echo "You can always reach a normal shell via another tty (Ctrl+Alt+F2) or 'exit' inside respire."
else
  echo "Skipped. You can launch the console manually any time by typing: respire"
fi

echo "[7/7] Done."
echo ""
echo "=== Installation complete ==="
echo "Run the console now with:  respire"
echo "Node agent status:         systemctl status respire-agent"
