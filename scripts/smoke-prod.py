"""Smoke checks against production API (no secrets in output)."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

BASE = "https://kitchen.alexklyvibe.ru"


def req(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {"detail": exc.reason}
        except json.JSONDecodeError:
            payload = {"detail": raw or exc.reason}
        err = payload.get("error")
        if isinstance(err, dict) and "code" not in payload:
            payload.setdefault("code", err.get("code"))
            payload.setdefault("detail", err.get("message"))
        return exc.code, payload


def main() -> int:
    results: list[str] = []
    email = f"smoke-{uuid4().hex[:8]}@example.com"
    password = f"Smoke!{uuid4().hex[:12]}"

    code, health = req("GET", "/health")
    results.append(f"health:{code} status={health.get('status')}")

    code, reg = req(
        "POST",
        "/api/v1/auth/register",
        {
            "email": email,
            "password": password,
            "workspace_name": "SmokeTest",
        },
    )
    results.append(f"register:{code} code={reg.get('code') or reg.get('detail')}")
    if code != 201:
        print("\n".join(results))
        return 1

    token = (reg.get("tokens") or {}).get("access_token")
    if not token:
        results.append("register:no_token")
        print("\n".join(results))
        return 1

    code, brands = req("GET", "/api/v1/brands", token=token)
    brand_count = len(brands) if isinstance(brands, list) else 0
    results.append(f"brands_list:{code} count={brand_count}")

    if brand_count == 0:
        code, created = req(
            "POST",
            "/api/v1/brands",
            {
                "name": "SmokeBrand",
                "niche": "Smoke test niche",
                "audience": "Test audience",
                "voice_tone": "Friendly",
                "offers": ["Offer A"],
                "timezone": "Europe/Moscow",
                "default_locale": "ru",
            },
            token=token,
        )
        results.append(f"brand_create:{code} err={created.get('code') or created.get('detail')}")
        if code != 201:
            print("\n".join(results))
            return 1
        brand_id = created["id"]
    else:
        brand_id = brands[0]["id"]

    code, patched = req(
        "PATCH",
        f"/api/v1/brands/{brand_id}",
        {
            "niche": "Smoke test niche",
            "audience": "Test audience",
            "voice_tone": "Friendly",
            "offers": ["Offer A"],
            "timezone": "Europe/Moscow",
            "default_locale": "ru",
        },
        token=token,
    )
    results.append(f"brand_kit:{code} err={patched.get('code') or patched.get('detail')}")

    code, oauth = req("POST", f"/api/v1/brands/{brand_id}/channels/instagram/oauth/start", token=token)
    oauth_url = oauth.get("auth_url") or oauth.get("authorization_url") or oauth.get("url") or ""
    has_meta = "facebook.com" in oauth_url
    results.append(f"ig_oauth_start:{code} meta_url={has_meta} err={oauth.get('code') or oauth.get('detail')}")

    code, job = req(
        "POST",
        f"/api/v1/brands/{brand_id}/plans/generate",
        {"year": 2026, "month": 9, "locale": "ru", "channels": ["telegram"], "targets": {"social_post": 2}},
        token=token,
    )
    job_id = job.get("job_id") or job.get("id")
    detail = job.get("detail") or job.get("message") or job.get("errors")
    results.append(f"plan_generate:{code} job={bool(job_id)} err={job.get('code') or detail}")

    if code == 202 and job_id:
        for _ in range(12):
            time.sleep(5)
            jcode, jbody = req("GET", f"/api/v1/jobs/{job_id}", token=token)
            status = jbody.get("status")
            if jcode == 200 and status in {"succeeded", "failed"}:
                err_code = jbody.get("error") or (jbody.get("result") or {}).get("error", {}).get("code")
                results.append(f"plan_job:{status} err={err_code}")
                break

    print("\n".join(results))
    hard_fail_prefixes = (
        "register:4",
        "register:5",
        "brand_create:4",
        "brand_create:5",
        "ig_oauth_start:4",
        "ig_oauth_start:5",
        "ig_oauth_start:503",
        "plan_generate:4",
        "plan_generate:5",
    )
    failed = [r for r in results if r.startswith(hard_fail_prefixes)]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
