from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

COVER_SIZE = 1080
BAR_RATIO = 0.28
MAX_HEADLINE_CHARS = 56
TEXT_MARGIN_X = 56
TEXT_PADDING_BOTTOM = 56


def _font_candidates() -> list[str]:
    return [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf",
        "Arial.ttf",
    ]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _font_candidates():
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        if len(lines) >= 2:
            break
        trial = word if not current else f"{current} {word}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
            current = word
        else:
            lines.append(word)
            current = ""
    if current and len(lines) < 2:
        lines.append(current)
    return lines[:2]


def _draw_bottom_gradient(scene: Image.Image) -> None:
    width, height = scene.size
    bar_h = max(int(height * BAR_RATIO), 1)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = overlay.load()
    for y in range(bar_h):
        # Fade from transparent at bar top → ~78% opaque at bottom.
        alpha = int(200 * ((y + 1) / bar_h))
        py = height - bar_h + y
        for x in range(width):
            pixels[x, py] = (0, 0, 0, alpha)
    scene.alpha_composite(overlay)


def export_square_1080(scene: Image.Image) -> bytes:
    canvas = scene.convert("RGBA").resize((COVER_SIZE, COVER_SIZE), Image.Resampling.LANCZOS)
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
    scene = scene.resize((COVER_SIZE, COVER_SIZE), Image.Resampling.LANCZOS)

    if logo_bytes:
        logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        max_w = 180
        ratio = max_w / max(logo.width, 1)
        logo = logo.resize(
            (int(logo.width * ratio), int(logo.height * ratio)),
            Image.Resampling.LANCZOS,
        )
        scene.paste(logo, (48, 48), logo)

    headline = " ".join((headline or "").split())[:MAX_HEADLINE_CHARS]
    if headline:
        _draw_bottom_gradient(scene)
        draw = ImageDraw.Draw(scene)
        font = _load_font(52)
        max_width = COVER_SIZE - TEXT_MARGIN_X * 2
        lines = _wrap_text(draw, headline, font, max_width)
        line_gap = 10
        heights: list[int] = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            heights.append(bbox[3] - bbox[1])
        block_h = sum(heights) + line_gap * max(len(lines) - 1, 0)
        y = COVER_SIZE - TEXT_PADDING_BOTTOM - block_h
        # Keep text inside bottom ~30% (upper ~70% is scene-only).
        min_y = int(COVER_SIZE * (1.0 - BAR_RATIO)) + 16
        if y < min_y:
            y = min_y
        for line, line_h in zip(lines, heights, strict=True):
            # Subtle shadow then white fill.
            draw.text((TEXT_MARGIN_X + 2, y + 2), line, fill=(0, 0, 0, 160), font=font)
            draw.text((TEXT_MARGIN_X, y), line, fill=(255, 255, 255, 255), font=font)
            y += line_h + line_gap

    buf = io.BytesIO()
    scene.convert("RGB").save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def placeholder_scene_bytes() -> bytes:
    img = Image.new("RGB", (COVER_SIZE, COVER_SIZE), color=(8, 18, 42))
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 120, 960, 960), outline=(0, 200, 255), width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
