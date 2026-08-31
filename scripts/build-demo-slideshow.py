"""Build overview demo video from Docs/demo/screenshots PNG slides."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "Docs" / "demo" / "screenshots"
OUT = ROOT / "Docs" / "demo" / "videos" / "demo-overview.mp4"

WIDTH = 1440
HEIGHT = 900
FPS = 30
HOLD_SEC = 3.2
FADE_SEC = 0.7

CAPTIONS: dict[str, str] = {
    "01-login.png": "Вход и регистрация",
    "02-dashboard.png": "Дашборд · KPI и мини-календарь",
    "03-calendar-slot.png": "Календарь · слоты по дням",
    "04-plan-existing.png": "Мастер плана · AI на месяц",
    "05-channels.png": "Каналы · Telegram, VK, Gmail",
    "06-queue.png": "Очередь публикаций",
    "07-analytics.png": "Аналитика по каналам",
    "08-ab.png": "A/B эксперименты",
    "09-settings.png": "Настройки · автопилот",
    "10-editor.png": "Редактор контента",
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def load_slide(path: Path) -> np.ndarray:
    pil = Image.open(path).convert("RGB")
    pil = pil.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    caption = CAPTIONS.get(path.name, path.stem)
    draw = ImageDraw.Draw(pil)
    font = _font(34)
    padding = 24
    bbox = draw.textbbox((0, 0), caption, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    box_h = text_h + padding * 2
    draw.rectangle([(0, HEIGHT - box_h), (WIDTH, HEIGHT)], fill=(15, 23, 42, 220))
    draw.text(
        ((WIDTH - text_w) // 2, HEIGHT - box_h + padding),
        caption,
        fill=(224, 242, 254),
        font=font,
    )

    rgb = np.array(pil)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def fade_frames(a: np.ndarray, b: np.ndarray, count: int) -> list[np.ndarray]:
    if count <= 0:
        return []
    out: list[np.ndarray] = []
    for i in range(1, count + 1):
        alpha = i / count
        blended = cv2.addWeighted(a, 1.0 - alpha, b, alpha, 0)
        out.append(blended)
    return out


def main() -> int:
    slides = sorted(SHOTS.glob("*.png"))
    if not slides:
        print(f"no screenshots in {SHOTS}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    hold_frames = int(HOLD_SEC * FPS)
    fade_frames_count = int(FADE_SEC * FPS)

    writer = cv2.VideoWriter(
        str(OUT),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        print("failed to open video writer", file=sys.stderr)
        return 1

    images = [load_slide(path) for path in slides]
    for index, frame in enumerate(images):
        for _ in range(hold_frames):
            writer.write(frame)
        if index + 1 < len(images):
            for transition in fade_frames(images[index], images[index + 1], fade_frames_count):
                writer.write(transition)

    writer.release()
    print(f"video: {OUT} ({len(slides)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
