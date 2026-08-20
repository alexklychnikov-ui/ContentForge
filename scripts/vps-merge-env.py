#!/usr/bin/env python3
"""Run on VPS: merge KEY=VALUE lines from stdin into /opt/contentforge/.env"""
import sys
from pathlib import Path

path = Path("/opt/contentforge/.env")
updates = {}
for line in sys.stdin:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    updates[key.strip()] = value

lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out: list[str] = []
seen: set[str] = set()
for line in lines:
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        out.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")

keys = ["OPENAI_API_KEY", "META_APP_SECRET", "META_APP_ID", "JWT_SECRET", "TOKEN_ENCRYPTION_KEY"]
data = {}
for line in path.read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        data[k.strip()] = v
for k in keys:
    v = data.get(k, "")
    print(f"{k}:{'empty' if not v.strip() else 'set'}")
