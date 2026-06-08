#!/bin/bash
# EC2 User Data script — runs once on first boot as root.
# Paste this into "Advanced Details > User data" when launching the EC2 instance.
#
# Prerequisites (do this before launching):
#   1. Push this repo to GitHub
#   2. Replace REPO_URL below with your repo URL
#
set -euo pipefail

REPO_URL="https://github.com/frantic-rgb/sensor-anomaly-detector.git"
APP_DIR="/opt/sensor-anomaly-detector"

# Install Docker
apt-get update -y
apt-get install -y docker.io git
systemctl enable --now docker

# Clone and build
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"
docker build -t sensor-anomaly-detector .

# Run on port 80
docker run -d \
  --name sensor-demo \
  -p 80:8000 \
  --restart unless-stopped \
  sensor-anomaly-detector

PUBLIC_IP=$(curl -sf http://169.254.169.254/latest/meta-data/public-ipv4 || echo "check AWS console")
echo "=== Demo running at http://$PUBLIC_IP ==="
