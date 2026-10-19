#!/usr/bin/env bash
# Install nginx vhost + certbot for your MoTranscript domain.
# DNS A record must point here (CDN proxy off / DNS-only) before issuing the cert.
set -euo pipefail

DOMAIN="${DOMAIN:-}"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ -z "$DOMAIN" ]]; then
  echo "Set DOMAIN=asr.example.com (your public hostname)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Substitute server_name in the nginx template
sed "s/asr.example.com/$DOMAIN/g" "$SCRIPT_DIR/nginx-motranscript.conf" \
  | sudo tee /etc/nginx/sites-available/motranscript >/dev/null
sudo ln -sfn /etc/nginx/sites-available/motranscript /etc/nginx/sites-enabled/motranscript
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

if [[ -z "$EMAIL" ]]; then
  echo "Set CERTBOT_EMAIL=you@example.com to obtain a certificate"
  exit 1
fi

sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect
echo "Certificate OK. If you use a CDN, switch SSL to Full (strict), then enable the proxy."
