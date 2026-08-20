from pathlib import Path
import secrets

from cryptography.fernet import Fernet


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


def main() -> None:
    root = Path(r"C:\Python\Projects\AIPlatform4ContentMarketing")
    merged = {**load(root / ".env"), **load(root / "backend" / ".env")}
    out = root / "deploy" / ".env.vps.tmp"
    lines = [
        f"POSTGRES_PASSWORD={merged.get('POSTGRES_PASSWORD') or secrets.token_urlsafe(24)}",
        f"JWT_SECRET={merged.get('JWT_SECRET') or secrets.token_hex(32)}",
        f"TOKEN_ENCRYPTION_KEY={merged.get('TOKEN_ENCRYPTION_KEY') or Fernet.generate_key().decode()}",
        f"OPENAI_API_KEY={merged.get('OPENAI_API_KEY', '')}",
        f"OPENAI_MODEL={merged.get('OPENAI_MODEL', 'gpt-4o-mini')}",
        "PUBLIC_API_URL=https://kitchen.alexklyvibe.ru",
        "PUBLIC_WEB_URL=https://kitchen.alexklyvibe.ru",
        f"META_APP_ID={merged.get('META_APP_ID', '1382440990693447')}",
        f"META_APP_SECRET={merged.get('META_APP_SECRET', '')}",
        "TELEGRAM_HTTPS_PROXY=",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written={out.name}")
    print(f"has_openai={bool(merged.get('OPENAI_API_KEY'))}")
    print(f"has_meta_secret={bool(merged.get('META_APP_SECRET'))}")


if __name__ == "__main__":
    main()
