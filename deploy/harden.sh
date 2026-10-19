#!/usr/bin/env bash
# Harden a fresh Ubuntu VPS for MoTranscript (run as ubuntu with passwordless sudo).
set -euo pipefail

SWAP_GB="${SWAP_GB:-2}"

echo "==> System update"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ufw fail2ban unattended-upgrades curl ca-certificates gnupg \
  nginx certbot python3-certbot-nginx git

echo "==> Swap ${SWAP_GB}G"
if ! swapon --show | grep -q .; then
  sudo fallocate -l "${SWAP_GB}G" /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024))
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "==> SSH harden"
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?KbdInteractiveAuthentication.*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
sudo systemctl reload ssh || sudo systemctl reload sshd

echo "==> UFW"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "==> fail2ban"
sudo systemctl enable --now fail2ban

echo "==> unattended-upgrades"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades || true

echo "==> Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker

echo "==> Done. Log out/in for docker group. Then: nproc && free -h"
nproc
free -h
df -h /
