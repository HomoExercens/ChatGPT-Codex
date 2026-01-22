from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


STEAM_ASSETS_VERSION = "steam_assets_v1"

CAPSULE_SPECS: list[tuple[str, tuple[int, int]]] = [
    ("capsule_header_920x430.png", (920, 430)),
    ("capsule_small_462x174.png", (462, 174)),
    ("capsule_main_1232x706.png", (1232, 706)),
    ("capsule_vertical_748x896.png", (748, 896)),
]


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _hex_color(raw: str) -> tuple[int, int, int]:
    s = str(raw or "").strip()
    if not s:
        return (11, 18, 32)
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join([c * 2 for c in s])
    if len(s) != 6:
        return (11, 18, 32)
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except Exception:  # noqa: BLE001
        return (11, 18, 32)


def _cover_fit(img: Image.Image, *, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGBA", size, (0, 0, 0, 255))

    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(round(src_w * scale))
    new_h = int(round(src_h * scale))
    resized = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

    left = max(0, (new_w - target_w) // 2)
    top = max(0, (new_h - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _find_font_paths() -> list[str]:
    candidates: list[str] = []

    env = os.environ.get("NEUROLEAGUE_STEAM_FONT_PATH")
    if env:
        candidates.append(env)

    candidates.extend(
        [
            # Common Linux paths (WSL/Ubuntu).
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            # Common Windows paths (GitHub Actions windows-latest).
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
        ]
    )

    out: list[str] = []
    for p in candidates:
        try:
            if Path(p).exists():
                out.append(p)
        except Exception:  # noqa: BLE001
            continue
    return out


def _load_font(size_px: int) -> ImageFont.ImageFont:
    size_px = max(10, int(size_px))
    for p in _find_font_paths():
        try:
            return ImageFont.truetype(p, size=size_px)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _fit_font_size(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    max_width: int,
    max_height: int,
    start_size: int,
) -> ImageFont.ImageFont:
    size = max(10, int(start_size))
    for _ in range(64):
        font = _load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        w = int(bbox[2] - bbox[0])
        h = int(bbox[3] - bbox[1])
        if w <= max_width and h <= max_height:
            return font
        size = max(10, int(size * 0.92))
    return _load_font(10)


def _add_bottom_gradient(img: Image.Image, *, strength: float = 0.65) -> None:
    w, h = img.size
    strength = max(0.0, min(1.0, float(strength)))

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = overlay.load()
    for y in range(h):
        t = y / max(1, h - 1)
        a = int(round(255 * strength * (t**2)))
        for x in range(w):
            px[x, y] = (0, 0, 0, a)
    img.alpha_composite(overlay)


def _draw_title(img: Image.Image, *, title: str) -> None:
    if not title.strip():
        return
    w, h = img.size
    draw = ImageDraw.Draw(img)

    pad_x = max(16, int(round(w * 0.05)))
    pad_y = max(14, int(round(h * 0.06)))

    max_text_w = w - pad_x * 2
    max_text_h = max(18, int(round(h * 0.18)))
    start_size = max(14, int(round(h * 0.18)))
    font = _fit_font_size(draw, text=title, max_width=max_text_w, max_height=max_text_h, start_size=start_size)

    bbox = draw.textbbox((0, 0), title, font=font)
    text_w = int(bbox[2] - bbox[0])
    text_h = int(bbox[3] - bbox[1])
    x = (w - text_w) // 2
    y = h - pad_y - text_h

    # Shadow for readability.
    for dx, dy in [(2, 2), (1, 2), (2, 1)]:
        draw.text((x + dx, y + dy), title, font=font, fill=(0, 0, 0, 160))
    draw.text((x, y), title, font=font, fill=(255, 255, 255, 255))


def _write_png(path: Path, img: Image.Image) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Determinism note: PNG compression metadata can vary across platforms; we keep the algorithm stable
    # and record output hashes for the current environment.
    img.save(path, format="PNG", optimize=True)
    b = path.read_bytes()
    return _sha256_bytes(b)


def _read_input(path: Path) -> tuple[Image.Image | None, dict]:
    if not path.exists():
        return None, {"path": str(path), "exists": False}
    b = path.read_bytes()
    try:
        img = Image.open(path).convert("RGBA")
    except Exception as e:  # noqa: BLE001
        return None, {"path": str(path), "exists": True, "error": str(e)}
    return img, {"path": str(path), "exists": True, "sha256": _sha256_bytes(b), "size": list(img.size)}


def export_capsules(
    *,
    input_img: Image.Image | None,
    bg_rgb: tuple[int, int, int],
    title: str,
    out_dir: Path,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "steam_assets_version": STEAM_ASSETS_VERSION,
        "title": title,
        "bg": "#{:02x}{:02x}{:02x}".format(*bg_rgb),
        "outputs": {},
    }

    for filename, (w, h) in CAPSULE_SPECS:
        base = Image.new("RGBA", (w, h), (*bg_rgb, 255))
        if input_img is not None:
            base = _cover_fit(input_img, size=(w, h))

        _add_bottom_gradient(base, strength=0.70 if h >= 400 else 0.75)
        _draw_title(base, title=title)
        out_path = out_dir / filename
        sha = _write_png(out_path, base)
        manifest["outputs"][filename] = {"size": [w, h], "sha256": sha}

    return manifest


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export Steam store capsule assets (placeholder-friendly).")
    p.add_argument("--input", dest="input", default=None, help="Background image path (sharecard/thumb). Optional.")
    p.add_argument("--title", dest="title", default=os.environ.get("NEUROLEAGUE_TITLE", "NeuroLeague"), help="Logo title text.")
    p.add_argument("--bg", dest="bg", default="#0b1220", help="Background color if no --input (hex, e.g. #0b1220).")
    p.add_argument("--out-dir", dest="out_dir", default="artifacts/steam_assets", help="Output directory.")
    p.add_argument("--write-manifest", dest="write_manifest", action="store_true", help="Write steam_assets_manifest.json.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    out_dir = Path(args.out_dir)
    bg = _hex_color(args.bg)
    title = str(args.title or "NeuroLeague").strip()

    input_img: Image.Image | None = None
    input_meta: dict | None = None
    if args.input:
        input_path = Path(args.input)
        input_img, input_meta = _read_input(input_path)

    manifest = export_capsules(input_img=input_img, bg_rgb=bg, title=title, out_dir=out_dir)
    if input_meta is not None:
        manifest["input"] = input_meta

    if args.write_manifest:
        (out_dir / "steam_assets_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
