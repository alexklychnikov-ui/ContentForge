#!/usr/bin/env bash
# On VPS: pull latest main and redeploy containers.
set -euo pipefail
cd /opt/contentforge
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -i /root/.ssh/contentforge_deploy -o IdentitiesOnly=yes}"
git pull --ff-only origin main
bash scripts/deploy-vps.sh
