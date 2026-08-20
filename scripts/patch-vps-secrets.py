"""Patch VPS .env from local files via scp (no secrets printed)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SSH = "test_vps4GbRam"
REMOTE_SCRIPT = "/opt/contentforge/scripts/vps-merge-env.py"


def load(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def merged_local() -> dict[str, str]:
    root = load(ROOT / ".env")
    backend = load(ROOT / "backend" / ".env")
    out = {**root}
    for key, value in backend.items():
        if value:
            out[key] = value
    return out


def main() -> None:
    local = merged_local()
    patch: dict[str, str] = {}
    if local.get("OPENAI_API_KEY"):
        patch["OPENAI_API_KEY"] = local["OPENAI_API_KEY"]
    model = local.get("OPENAI_MODEL_TEXT") or local.get("OPENAI_MODEL")
    if model:
        patch["OPENAI_MODEL"] = model
    if local.get("META_APP_SECRET"):
        patch["META_APP_SECRET"] = local["META_APP_SECRET"]
    if local.get("META_APP_ID"):
        patch["META_APP_ID"] = local["META_APP_ID"]

    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(ROOT / "scripts" / "vps-merge-env.py"), f"{SSH}:{REMOTE_SCRIPT}"],
        check=True,
    )
    payload = "\n".join(f"{k}={v}" for k, v in patch.items())
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", SSH, "python3", REMOTE_SCRIPT],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    print(proc.stdout.strip())
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)
    if patch:
        subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                SSH,
                "cd /opt/contentforge && docker compose -f docker-compose.prod.yml up -d --force-recreate api worker beat",
            ],
            check=True,
        )
        print("recreated=api,worker,beat")


if __name__ == "__main__":
    main()
