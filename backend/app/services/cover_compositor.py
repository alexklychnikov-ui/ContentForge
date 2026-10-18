from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def export_square_1080(scene: Image.Image) -> bytes:
    canvas = scene.convert("RGBA").resize((1080, 1080), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def composite_cover(
    scene_bytes: bytes,
    *,
    headline: str = "",
    logo_bytes: bytes | None = None,
) -> bytes:
    scene = Image.open(io.BytesIO(scene_bytes)).convert("RGBA")
    scene = scene.resize((1024, 1024), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(scene)

    if logo_bytes:
        logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        max_w = 180
        ratio = max_w / max(logo.width, 1)
        logo = logo.resize((int(logo.width * ratio), int(logo.height * ratio)), Image.Resampling.LANCZOS)
        scene.paste(logo, (48, 48), logo)

    headline = " ".join((headline or "").split())[:48]
    if headline:
        font = _load_font(42)
        draw.text((48, 900), headline, fill=(255, 255, 255, 255), font=font)

    return export_square_1080(scene)


def placeholder_scene_bytes() -> bytes:
    img = Image.new("RGB", (1024, 1024), color=(8, 18, 42))
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 120, 900, 900), outline=(0, 200, 255), width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
