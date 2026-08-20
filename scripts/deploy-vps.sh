#!/usr/bin/env bash
# Run on VPS as root from /opt/contentforge after .env exists.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env in $ROOT — copy from deploy/env.production.example"
  exit 1
fi

docker compose -f docker-compose.prod.yml pull postgres redis 2>/dev/null || true
docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d

install -m 644 deploy/nginx/kitchen.alexklyvibe.ru.conf /etc/nginx/sites-available/kitchen.alexklyvibe.ru
ln -sf /etc/nginx/sites-available/kitchen.alexklyvibe.ru /etc/nginx/sites-enabled/kitchen.alexklyvibe.ru
nginx -t
systemctl reload nginx

echo "OK: $(curl -s -o /dev/null -w '%{http_code}' https://kitchen.alexklyvibe.ru/health)"
