"""Capture demo screenshots and plan-creation video from production (admin account)."""
from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://kitchen.alexklyvibe.ru"
EMAIL = "admin@testfullcrm.alexklyvibe.ru"
PASSWORD = "Test1234!"

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "Docs" / "demo" / "screenshots"
VIDEOS = ROOT / "Docs" / "demo" / "videos"


def api_post(path: str, body: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(path: str, token: str) -> object:
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_session() -> tuple[dict, str]:
    auth = api_post("/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    token = auth["tokens"]["access_token"]
    brands = api_get("/api/v1/brands", token)
    brand_id = brands[0]["id"]
    session = {
        "user": auth["user"],
        "workspace": auth["workspace"],
        "tokens": auth["tokens"],
    }
    return session, brand_id


def inject(page, session: dict, brand_id: str) -> None:
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.evaluate(
        """({ session, brandId }) => {
            localStorage.setItem('cf_session', JSON.stringify(session));
            localStorage.setItem('cf_brand_id', brandId);
        }""",
        {"session": session, "brandId": brand_id},
    )


def wait_brand(page) -> None:
    page.goto(f"{BASE}/", wait_until="networkidle")
    page.wait_for_selector('select[aria-label="Переключатель бренда"]', timeout=30_000)


def shot(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / name), full_page=True)
    print(f"screenshot: {name}")


def set_calendar_month(page, year: int, month: int) -> None:
    page.goto(f"{BASE}/calendar", wait_until="networkidle")
    nums = page.locator('input[type="number"]')
    nums.nth(0).fill(str(year))
    nums.nth(1).fill(str(month))
    page.wait_for_timeout(800)


def set_plan_form(page, year: int, month: int, posts: int, emails: int) -> None:
    page.goto(f"{BASE}/plan", wait_until="networkidle")
    nums = page.locator("main .panel input[type='number']")
    nums.nth(0).fill(str(year))
    nums.nth(1).fill(str(month))
    checks = page.locator("main .panel input[type='checkbox']")
    checks.nth(1).check()
    checks.nth(2).check()
    nums.nth(2).fill(str(posts))
    nums.nth(4).fill(str(emails))
    page.wait_for_timeout(500)


def capture_screenshots(page, session: dict, brand_id: str) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle")
    shot(page, "01-login.png")

    inject(page, session, brand_id)
    wait_brand(page)
    shot(page, "02-dashboard.png")

    set_calendar_month(page, 2026, 8)
    day = page.locator('[data-testid="month-grid"] button[data-date="2026-08-03"]')
    if day.count():
        day.click()
        page.wait_for_timeout(600)
    shot(page, "03-calendar-slot.png")

    page.goto(f"{BASE}/plan", wait_until="networkidle")
    shot(page, "04-plan-existing.png")

    page.goto(f"{BASE}/channels", wait_until="networkidle")
    shot(page, "05-channels.png")

    page.goto(f"{BASE}/queue", wait_until="networkidle")
    shot(page, "06-queue.png")

    page.goto(f"{BASE}/analytics", wait_until="networkidle")
    shot(page, "07-analytics.png")

    page.goto(f"{BASE}/ab", wait_until="networkidle")
    shot(page, "08-ab.png")

    page.goto(f"{BASE}/settings", wait_until="networkidle")
    shot(page, "09-settings.png")

    page.goto(f"{BASE}/content", wait_until="networkidle")
    shot(page, "10-editor.png")


def record_plan_video(page, session: dict, brand_id: str) -> None:
    VIDEOS.mkdir(parents=True, exist_ok=True)
    inject(page, session, brand_id)
    wait_brand(page)

    page.goto(f"{BASE}/plan", wait_until="networkidle")
    page.wait_for_timeout(1000)
    set_plan_form(page, year=2026, month=11, posts=8, emails=2)

    page.get_by_role("button", name="Сгенерировать").click()
    page.wait_for_selector("text=Идёт генерация", timeout=20_000)

    deadline = time.time() + 180
    while time.time() < deadline:
        approve = page.get_by_role("button", name="Утвердить план")
        if approve.count() > 0 and approve.is_enabled():
            approve.click()
            page.wait_for_timeout(1500)
            break
        if page.locator("table tbody tr").count() > 2:
            enabled = page.get_by_role("button", name="Сгенерировать")
            if enabled.count() and enabled.is_enabled():
                break
        page.wait_for_timeout(3000)

    page.wait_for_timeout(1500)
    set_calendar_month(page, 2026, 11)
    page.wait_for_timeout(2000)


def main() -> None:
    session, brand_id = fetch_session()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        ctx_shots = browser.new_context(viewport={"width": 1440, "height": 900})
        page_shots = ctx_shots.new_page()
        capture_screenshots(page_shots, session, brand_id)
        ctx_shots.close()

        ctx_vid = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(VIDEOS),
            record_video_size={"width": 1440, "height": 900},
        )
        page_vid = ctx_vid.new_page()
        record_plan_video(page_vid, session, brand_id)
        video = page_vid.video
        ctx_vid.close()
        browser.close()

        if video:
            raw = video.path()
            if raw:
                dest = VIDEOS / "plan-create.webm"
                if dest.exists():
                    dest.unlink()
                shutil.move(raw, dest)
                print(f"video: {dest.name}")

    print("done")


if __name__ == "__main__":
    main()
