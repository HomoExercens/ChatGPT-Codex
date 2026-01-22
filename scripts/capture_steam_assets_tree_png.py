from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        try:
            if Path(p).exists():
                return ImageFont.truetype(p, size=int(size))
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _render_text_png(*, lines: list[str], out_path: Path) -> None:
    font = _load_font(16)
    pad = 16
    line_h = 22
    width = 1000
    height = pad * 2 + line_h * max(1, len(lines))

    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)
    y = pad
    for line in lines:
        draw.text((pad, y), line, font=font, fill=(20, 20, 20))
        y += line_h

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out_dir = repo / "artifacts" / "steam_assets"

    subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "export_steam_assets.py"),
            "--out-dir",
            str(out_dir),
            "--write-manifest",
        ],
        check=True,
        cwd=str(repo),
    )

    files = sorted([p.name for p in out_dir.iterdir() if p.is_file()])
    lines = ["artifacts/steam_assets/"] + [f"  {name}" for name in files]
    _render_text_png(lines=lines, out_path=repo / "docs" / "screenshots" / "56_steam_assets_tree.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

