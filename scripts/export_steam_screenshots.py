from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def _fit_letterbox(img: Image.Image, *, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    src_w, src_h = img.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", size, (0, 0, 0))

    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    resized = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS).convert(
        "RGB"
    )

    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    x = (target_w - new_w) // 2
    y = (target_h - new_h) // 2
    canvas.paste(resized, (x, y))
    return canvas


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Export Steam screenshot candidates (1920x1080 letterbox) from docs/screenshots."
    )
    p.add_argument(
        "--in-dir",
        dest="in_dir",
        default="docs/screenshots",
        help="Input directory containing screenshots.",
    )
    p.add_argument(
        "--out-dir",
        dest="out_dir",
        default="artifacts/steam_assets/screenshots",
        help="Output directory for Steam screenshots.",
    )
    p.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=8,
        help="Max screenshots to export (default 8).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = sorted([p for p in in_dir.glob("*.png") if p.is_file()])
    exported: list[dict] = []
    limit = max(0, int(args.limit))

    for i, p in enumerate(candidates[:limit], start=1):
        img = Image.open(p)
        out = _fit_letterbox(img, size=(1920, 1080))
        name = f"{i:02d}.png"
        out_path = out_dir / name
        out.save(out_path, format="PNG", optimize=True)
        exported.append({"src": str(p), "out": str(out_path)})

    manifest = {"exported": exported}
    (out_dir / "screenshots_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

