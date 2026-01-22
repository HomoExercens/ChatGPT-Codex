from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import html as html_lib
from io import BytesIO
import os
from pathlib import Path
import subprocess
from typing import Any, Literal
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from neuroleague_api.core.config import Settings
from neuroleague_api.deps import CurrentUserId, DBSession
from neuroleague_api.models import Event, Match, Replay, RenderJob
from neuroleague_api.rate_limit import check_rate_limit_dual
from neuroleague_api.ray_runtime import ensure_ray
from neuroleague_api.storage import ensure_artifacts_dir, load_replay_json
from neuroleague_api.storage_backend import get_storage_backend

router = APIRouter(prefix="/api/replays", tags=["replays"])


def _asset_response(*, key: str, media_type: str):
    backend = get_storage_backend()
    try:
        local = backend.local_path(key=key)
    except Exception:  # noqa: BLE001
        local = None
    if local is not None and local.exists():
        return FileResponse(path=str(local), media_type=media_type, filename=local.name)
    try:
        if backend.exists(key=key):
            return RedirectResponse(url=backend.public_url(key=key), status_code=307)
    except Exception:  # noqa: BLE001
        pass
    return None


@router.get("/{replay_id}")
def get_replay(
    replay_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")
    return load_replay_json(artifact_path=replay.artifact_path)


class BookmarkRequest(BaseModel):
    t: int = Field(ge=0)
    label: str = Field(default="Bookmark", min_length=1, max_length=32)


@router.post("/{replay_id}/bookmark")
def bookmark(
    replay_id: str,
    req: BookmarkRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> dict[str, Any]:
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")

    db.add(
        Event(
            id=f"evt_{uuid4().hex}",
            user_id=user_id,
            type="replay_bookmark",
            payload_json=f'{{"replay_id":"{replay_id}","t":{req.t},"label":{req.label!r}}}',
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    return {"ok": True}


def _safe_font(size: int, *, bold: bool) -> Any:
    from PIL import ImageFont

    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, *, max_len: int) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        if sum(len(x) for x in cur) + len(cur) + len(w) <= max_len:
            cur.append(w)
            continue
        lines.append(" ".join(cur))
        cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines


def _render_sharecard_png_v1(*, replay_payload: dict[str, Any], match: Match) -> bytes:
    from PIL import Image, ImageDraw

    w, h = 1200, 630
    img = Image.new("RGB", (w, h), (15, 23, 42))  # slate-900
    draw = ImageDraw.Draw(img)

    brand = (37, 99, 235)
    accent = (139, 92, 246)

    header = replay_payload.get("header", {}) or {}
    end = replay_payload.get("end_summary", {}) or {}
    ruleset = str(header.get("ruleset_version") or Settings().ruleset_version)
    digest = str(replay_payload.get("digest") or "")[:12]
    winner = str(end.get("winner") or "draw")

    outcome = "DRAW"
    outcome_color = (148, 163, 184)
    if winner == "A":
        outcome = "VICTORY"
        outcome_color = (34, 197, 94)
    elif winner == "B":
        outcome = "DEFEAT"
        outcome_color = (248, 113, 113)

    elo_delta = int(getattr(match, "elo_delta_a", 0) or 0)
    elo_text = f"Elo Δ {elo_delta:+d}"

    highlights = replay_payload.get("highlights") or []
    top = highlights[0] if isinstance(highlights, list) and highlights else {}
    title = str(top.get("title") or "Turning Point")
    summary = str(top.get("summary") or "")
    tags = [t for t in (top.get("tags") or []) if isinstance(t, str)]
    tags = [t for t in tags if not t.startswith("type:")][:4]

    # Background accents
    draw.rounded_rectangle(
        (40, 40, w - 40, h - 40),
        radius=36,
        fill=(17, 24, 39),
        outline=(30, 41, 59),
        width=2,
    )
    draw.rounded_rectangle((64, 84, 64 + 520, 84 + 14), radius=8, fill=brand)
    draw.rounded_rectangle((w - 64 - 520, 84, w - 64, 84 + 14), radius=8, fill=accent)

    f_title = _safe_font(60, bold=True)
    f_sub = _safe_font(22, bold=False)
    f_kpi = _safe_font(34, bold=True)
    f_body = _safe_font(24, bold=False)
    f_tag = _safe_font(20, bold=True)

    draw.text((72, 112), "NEUROLEAGUE", font=f_sub, fill=(148, 163, 184))
    draw.text((72, 144), outcome, font=f_title, fill=outcome_color)
    draw.text((72, 220), elo_text, font=f_kpi, fill=(226, 232, 240))

    draw.text((72, 276), f"Ruleset: {ruleset}", font=f_sub, fill=(148, 163, 184))
    draw.text((72, 306), f"Match: {match.id}", font=f_sub, fill=(148, 163, 184))
    if digest:
        draw.text((72, 336), f"Digest: {digest}", font=f_sub, fill=(100, 116, 139))

    # Highlight block
    draw.rounded_rectangle(
        (72, 378, w - 72, h - 88),
        radius=28,
        fill=(15, 23, 42),
        outline=(30, 41, 59),
        width=2,
    )
    draw.text((96, 404), "Turning Point", font=f_sub, fill=(148, 163, 184))
    draw.text((96, 438), title, font=_safe_font(34, bold=True), fill=(226, 232, 240))

    y = 488
    for line in _wrap_text(summary, max_len=54)[:3]:
        draw.text((96, y), line, font=f_body, fill=(203, 213, 225))
        y += 32

    # Tags
    tag_x = 96
    tag_y = h - 140
    for tg in tags:
        tw = draw.textlength(tg, font=f_tag)
        box = (tag_x, tag_y, tag_x + tw + 22, tag_y + 34)
        draw.rounded_rectangle(box, radius=14, fill=(30, 41, 59))
        draw.text((tag_x + 11, tag_y + 6), tg, font=f_tag, fill=(226, 232, 240))
        tag_x += int(tw) + 34
        if tag_x > w - 220:
            break

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _sharecard_html_v2(
    *,
    replay_payload: dict[str, Any],
    match: Match,
    theme: Literal["dark", "light"],
    locale: Literal["en", "ko"],
) -> str:
    header = replay_payload.get("header", {}) or {}
    end = replay_payload.get("end_summary", {}) or {}
    ruleset = str(header.get("ruleset_version") or Settings().ruleset_version)
    mode = str(header.get("mode") or getattr(match, "mode", "1v1") or "1v1")
    digest = str(replay_payload.get("digest") or "")[:12]
    winner = str(end.get("winner") or "draw")

    highlights = replay_payload.get("highlights") or []
    top = highlights[0] if isinstance(highlights, list) and highlights else {}
    title = str(top.get("title") or ("전환점" if locale == "ko" else "Turning Point"))
    summary = str(top.get("summary") or "")
    raw_tags = [t for t in (top.get("tags") or []) if isinstance(t, str)]
    chips: list[str] = []
    for tg in raw_tags:
        if tg.startswith("type:"):
            continue
        if tg.startswith("team:") or tg.startswith("lead:"):
            continue
        chips.append(tg.replace("synergy:", "").replace("item:", "").replace("_", " "))
    chips = chips[:5]

    outcome = "DRAW"
    outcome_ko = "무승부"
    outcome_color = "rgb(148 163 184)"
    if winner == "A":
        outcome = "VICTORY"
        outcome_ko = "승리"
        outcome_color = "rgb(34 197 94)"
    elif winner == "B":
        outcome = "DEFEAT"
        outcome_ko = "패배"
        outcome_color = "rgb(248 113 113)"

    elo_delta = int(getattr(match, "elo_delta_a", 0) or 0)
    elo_text = f"{elo_delta:+d}"

    safe = html_lib.escape
    mode_label = "Team (3v3)" if mode == "team" else "1v1"
    mode_label_ko = "팀전 (3v3)" if mode == "team" else "1v1"

    bg = "rgb(248 250 252)" if theme == "light" else "rgb(var(--nl-lab-900))"
    panel = "rgba(255,255,255,0.88)" if theme == "light" else "rgba(2,6,23,0.72)"
    panel_border = (
        "rgba(148,163,184,0.25)" if theme == "light" else "rgba(148,163,184,0.18)"
    )
    text = "rgb(15 23 42)" if theme == "light" else "rgb(226 232 240)"
    muted = "rgb(71 85 105)" if theme == "light" else "rgb(148 163 184)"

    chips_html = "".join(
        f'<span class="chip">{safe(c)}</span>' for c in chips if c.strip()
    )
    if not chips_html:
        chips_html = f'<span class="chip">{safe(mode_label if locale != "ko" else mode_label_ko)}</span>'

    return f"""<!doctype html>
<html lang="{safe(locale)}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Share Card</title>
    <style>
      :root {{
        --nl-brand-50: 239 246 255;
        --nl-brand-100: 219 234 254;
        --nl-brand-200: 191 219 254;
        --nl-brand-300: 147 197 253;
        --nl-brand-400: 96 165 250;
        --nl-brand-500: 59 130 246;
        --nl-brand-600: 37 99 235;
        --nl-brand-700: 29 78 216;
        --nl-brand-900: 30 58 138;
        --nl-lab-50: 248 250 252;
        --nl-lab-900: 15 23 42;
        --nl-accent-200: 221 214 254;
        --nl-accent-500: 139 92 246;
        --nl-accent-700: 109 40 217;
      }}
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; padding: 0; width: 1200px; height: 630px; }}
      body {{
        background: {bg};
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      }}
      .frame {{
        width: 1200px;
        height: 630px;
        padding: 36px;
        background: linear-gradient(90deg, rgb(var(--nl-brand-600)), rgb(var(--nl-accent-500)));
      }}
      .card {{
        width: 100%;
        height: 100%;
        border-radius: 36px;
        overflow: hidden;
        position: relative;
        background: {panel};
        border: 1px solid {panel_border};
      }}
      .grid {{
        position: absolute;
        inset: 0;
        opacity: {0.16 if theme == "dark" else 0.06};
        background-image: radial-gradient(rgba(148,163,184,0.9) 1px, transparent 1px);
        background-size: 24px 24px;
        pointer-events: none;
      }}
      .glow {{
        position: absolute;
        width: 520px;
        height: 520px;
        border-radius: 999px;
        filter: blur(70px);
        opacity: {0.22 if theme == "dark" else 0.18};
        background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.55), rgba(255,255,255,0));
        top: -180px;
        right: -180px;
        pointer-events: none;
      }}
      .content {{
        position: relative;
        z-index: 2;
        padding: 30px 34px;
        height: 100%;
        display: flex;
        flex-direction: column;
        gap: 18px;
      }}
      .top {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
      }}
      .brand {{
        display: flex;
        flex-direction: column;
        gap: 4px;
        min-width: 0;
      }}
      .brand .name {{
        font-weight: 900;
        letter-spacing: 0.08em;
        font-size: 14px;
        color: {muted};
      }}
      .brand .subtitle {{
        font-weight: 700;
        font-size: 18px;
        color: {text};
        line-height: 1.1;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 720px;
      }}
      .pill {{
        padding: 8px 12px;
        border-radius: 999px;
        font-weight: 800;
        font-size: 12px;
        color: {text};
        border: 1px solid {panel_border};
        background: rgba(255,255,255,0.18);
      }}
      .main {{
        flex: 1;
        display: grid;
        grid-template-columns: 1.05fr 1fr;
        gap: 22px;
        min-height: 0;
      }}
      .block {{
        border-radius: 28px;
        border: 1px solid {panel_border};
        background: rgba(255,255,255,0.06);
        padding: 22px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        min-height: 0;
      }}
      .outcome {{
        font-weight: 950;
        font-size: 56px;
        letter-spacing: -0.02em;
        color: {outcome_color};
        line-height: 1;
      }}
      .kpi {{
        display: flex;
        align-items: baseline;
        gap: 10px;
        flex-wrap: wrap;
      }}
      .kpi .label {{
        font-weight: 800;
        font-size: 14px;
        color: {muted};
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }}
      .kpi .value {{
        font-weight: 900;
        font-size: 34px;
        color: {text};
      }}
      .meta {{
        display: flex;
        flex-direction: column;
        gap: 6px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 13px;
        color: {muted};
      }}
      .sectionTitle {{
        font-weight: 900;
        font-size: 14px;
        color: {muted};
        text-transform: uppercase;
        letter-spacing: 0.12em;
      }}
      .hlTitle {{
        font-weight: 900;
        font-size: 30px;
        color: {text};
        line-height: 1.1;
      }}
      .hlSummary {{
        font-size: 18px;
        color: {muted};
        line-height: 1.35;
        display: -webkit-box;
        -webkit-line-clamp: 4;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }}
      .chips {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: auto;
      }}
      .chip {{
        padding: 8px 12px;
        border-radius: 999px;
        border: 1px solid {panel_border};
        background: rgba(255,255,255,0.10);
        color: {text};
        font-weight: 800;
        font-size: 12px;
        letter-spacing: 0.02em;
        text-transform: uppercase;
      }}
      .footer {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        font-size: 13px;
        color: {muted};
      }}
      .route {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-weight: 800;
      }}
    </style>
  </head>
  <body>
    <div class="frame">
      <div class="card">
        <div class="grid"></div>
        <div class="glow"></div>
        <div class="content">
          <div class="top">
            <div class="brand">
              <div class="name">CREATURE LAB · AUTO-BATTLE LEAGUE</div>
              <div class="subtitle">{safe(mode_label_ko if locale == "ko" else mode_label)} · {safe(ruleset)}</div>
            </div>
            <div class="pill">{safe(outcome_ko if locale == "ko" else outcome)}</div>
          </div>
          <div class="main">
            <div class="block">
              <div class="outcome">{safe(outcome_ko if locale == "ko" else outcome)}</div>
              <div class="kpi">
                <div class="label">ELO Δ</div>
                <div class="value">{safe(elo_text)}</div>
              </div>
              <div class="meta">
                <div>match_id: {safe(match.id)}</div>
                <div>digest: {safe(digest or "unknown")}</div>
              </div>
              <div class="chips">
                {chips_html}
              </div>
            </div>
            <div class="block">
              <div class="sectionTitle">{safe("전환점" if locale == "ko" else "Turning Point")}</div>
              <div class="hlTitle">{safe(title)}</div>
              <div class="hlSummary">{safe(summary) if summary else safe("—")}</div>
              <div class="footer">
                <div class="route">/replay/{safe(match.id)}</div>
                <div>{safe("공유 카드 v2" if locale == "ko" else "Share Card v2")}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""


def _render_sharecard_png_v2(*, html: str, out_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    node_cwd = repo_root / "apps" / "web"
    script = node_cwd / "scripts" / "render_sharecard.mjs"
    if not script.exists():
        raise RuntimeError("sharecard renderer script missing")

    tmp_path = out_path.with_suffix(".tmp.png")
    cmd = [
        "node",
        str(script),
        "--out",
        str(tmp_path),
        "--width",
        "1200",
        "--height",
        "630",
    ]

    def _run() -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            cmd,
            input=html.encode("utf-8"),
            cwd=str(node_cwd),
            capture_output=True,
            check=False,
        )

    proc = _run()
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="ignore")
        if "Executable doesn't exist" in stderr or "playwright install" in stderr:
            install = subprocess.run(
                ["npx", "playwright", "install", "chromium"],
                cwd=str(node_cwd),
                capture_output=True,
                check=False,
            )
            if install.returncode == 0:
                proc = _run()
                stderr = (proc.stderr or b"").decode("utf-8", errors="ignore")
        if proc.returncode != 0:
            raise RuntimeError(stderr.strip() or "sharecard v2 render failed")

    if not tmp_path.exists():
        raise RuntimeError("sharecard v2 renderer did not write output")
    tmp_path.replace(out_path)


@router.get("/{replay_id}/sharecard", response_model=None)
def sharecard(
    replay_id: str,
    request: Request,
    theme: Literal["dark", "light"] = "dark",
    locale: Literal["en", "ko"] = "en",
    async_: int = Query(default=1, alias="async", ge=0, le=1),
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> Any:
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")

    payload = load_replay_json(artifact_path=replay.artifact_path)
    digest = str(replay.digest or payload.get("digest") or "")
    safe_digest = digest[:12] if digest else "unknown"
    key_v2 = f"sharecards/sharecard_v2_{replay_id}_{safe_digest}_{theme}_{locale}.png"
    key_v1 = f"sharecards/sharecard_v1_{replay_id}_{safe_digest}.png"

    cached = _asset_response(key=key_v2, media_type="image/png")
    if cached is not None:
        return cached
    cached = _asset_response(key=key_v1, media_type="image/png")
    if cached is not None:
        return cached

    if async_:
        kind = "sharecard"
        key_msg = f"sharecard_v2:{digest}:{theme}:{locale}"
        key = hashlib.sha256(key_msg.encode("utf-8")).hexdigest()
        settings = Settings()
        check_rate_limit_dual(
            user_id=user_id,
            request=request,
            action="render_jobs",
            per_minute_user=int(settings.rate_limit_render_jobs_per_minute),
            per_hour_user=int(settings.rate_limit_render_jobs_per_hour),
            per_minute_ip=int(settings.rate_limit_render_jobs_per_minute_ip),
            per_hour_ip=int(settings.rate_limit_render_jobs_per_hour_ip),
            extra_detail={"kind": "sharecard"},
        )

        existing = db.scalar(
            select(RenderJob)
            .where(RenderJob.user_id == user_id)
            .where(RenderJob.cache_key == key)
            .order_by(RenderJob.created_at.desc())
            .limit(1)
        )
        if existing and existing.status in ("queued", "running", "done"):
            return JSONResponse(
                status_code=202,
                content={
                    "job_id": existing.id,
                    "status": existing.status,
                    "cache_key": key,
                },
            )

        now = datetime.now(UTC)
        job = RenderJob(
            id=f"rj_{uuid4().hex}",
            user_id=user_id,
            kind=kind,
            target_replay_id=replay_id,
            target_match_id=replay.match_id,
            params_json=orjson.dumps({"theme": theme, "locale": locale}).decode(
                "utf-8"
            ),
            cache_key=key,
            status="queued",
            progress=0,
            ray_job_id=None,
            artifact_path=None,
            error_message=None,
            created_at=now,
            finished_at=None,
        )
        db.add(job)
        db.commit()

        if settings.desktop_mode:
            return JSONResponse(
                status_code=202,
                content={"job_id": job.id, "status": job.status, "cache_key": key},
            )

        ensure_ray()
        from neuroleague_api.ray_tasks import render_sharecard_job

        obj_ref = render_sharecard_job.remote(
            job_id=job.id,
            replay_id=replay_id,
            theme=theme,
            locale=locale,
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
        )
        job.ray_job_id = obj_ref.hex()
        db.add(job)
        db.commit()
        return JSONResponse(
            status_code=202,
            content={"job_id": job.id, "status": job.status, "cache_key": key},
        )

    backend = get_storage_backend()
    if not backend.exists(key=key_v2):
        html = _sharecard_html_v2(
            replay_payload=payload, match=match, theme=theme, locale=locale
        )
        try:
            local = backend.local_path(key=key_v2)
            if local is not None:
                _render_sharecard_png_v2(html=html, out_path=local)
            else:
                from tempfile import TemporaryDirectory

                with TemporaryDirectory(prefix="neuroleague_sharecard_") as tmpdir:
                    tmp_path = (
                        Path(tmpdir) / f"sharecard_v2_{replay_id}_{safe_digest}.png"
                    )
                    _render_sharecard_png_v2(html=html, out_path=tmp_path)
                    backend.put_file(
                        key=key_v2, path=tmp_path, content_type="image/png"
                    )
        except Exception:  # noqa: BLE001
            if not backend.exists(key=key_v1):
                backend.put_bytes(
                    key=key_v1,
                    data=_render_sharecard_png_v1(replay_payload=payload, match=match),
                    content_type="image/png",
                )
            cached_fallback = _asset_response(key=key_v1, media_type="image/png")
            if cached_fallback is not None:
                return cached_fallback
            raise HTTPException(status_code=500, detail="Failed to store sharecard")

    cached_v2 = _asset_response(key=key_v2, media_type="image/png")
    if cached_v2 is not None:
        return cached_v2
    raise HTTPException(status_code=500, detail="Failed to store sharecard")


@router.post("/{replay_id}/export-sharecard")
def export_sharecard_post(
    replay_id: str, user_id: str = CurrentUserId, db: Session = DBSession
) -> dict[str, Any]:
    # Backwards compatible endpoint (v1 placeholder → real generator).
    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")

    payload = load_replay_json(artifact_path=replay.artifact_path)
    digest = str(replay.digest or payload.get("digest") or "")
    safe_digest = digest[:12] if digest else "unknown"

    root = ensure_artifacts_dir()
    out_dir = root / "sharecards"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path_v2 = out_dir / f"sharecard_v2_{replay_id}_{safe_digest}_dark_en.png"
    out_path_v1 = out_dir / f"sharecard_v1_{replay_id}_{safe_digest}.png"
    if not out_path_v2.exists():
        html = _sharecard_html_v2(
            replay_payload=payload, match=match, theme="dark", locale="en"
        )
        try:
            _render_sharecard_png_v2(html=html, out_path=out_path_v2)
        except Exception:  # noqa: BLE001
            if not out_path_v1.exists():
                out_path_v1.write_bytes(
                    _render_sharecard_png_v1(replay_payload=payload, match=match)
                )
            return {
                "ok": True,
                "replay_id": replay_id,
                "artifact_path": str(out_path_v1),
                "fallback": "v1",
            }

    return {"ok": True, "replay_id": replay_id, "artifact_path": str(out_path_v2)}


class RenderJobCreated(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    cache_key: str


class ThumbnailJobRequest(BaseModel):
    start: float = 0.0
    end: float | None = None
    scale: int = Field(default=1, ge=1, le=2)
    theme: Literal["dark", "light"] = "dark"


@router.post("/{replay_id}/thumbnail_jobs", response_model=RenderJobCreated)
def create_thumbnail_job(
    replay_id: str,
    request: Request,
    req: ThumbnailJobRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> RenderJobCreated:
    from neuroleague_api.clip_render import cache_key, clamp_clip_params
    from neuroleague_api.moderation import ensure_not_soft_banned

    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")

    ensure_not_soft_banned(db, user_id=user_id)

    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="render_jobs",
        per_minute_user=int(settings.rate_limit_render_jobs_per_minute),
        per_hour_user=int(settings.rate_limit_render_jobs_per_hour),
        per_minute_ip=int(settings.rate_limit_render_jobs_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_render_jobs_per_hour_ip),
        extra_detail={"kind": "thumbnail"},
    )

    payload = load_replay_json(artifact_path=replay.artifact_path)
    digest = str(replay.digest or payload.get("digest") or "")
    if not digest:
        raise HTTPException(status_code=500, detail="Replay digest missing")

    start_tick, end_tick, _fps, scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=req.start,
        end_sec=req.end,
        fps=10,
        scale=req.scale,
        max_duration_sec=12.0,
    )
    key = cache_key(
        replay_digest=digest,
        kind="thumbnail",
        start_tick=start_tick,
        end_tick=end_tick,
        fps=1,
        scale=scale,
        theme=req.theme,
    )

    existing = db.scalar(
        select(RenderJob)
        .where(RenderJob.user_id == user_id)
        .where(RenderJob.cache_key == key)
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )
    if existing and existing.status in ("queued", "running", "done"):
        return RenderJobCreated(
            job_id=existing.id, status=existing.status, cache_key=key
        )  # type: ignore[arg-type]

    asset_key = f"clips/thumbnails/thumb_{replay_id}_{key[:16]}.png"
    backend = get_storage_backend()
    now = datetime.now(UTC)
    if backend.exists(key=asset_key):
        job = RenderJob(
            id=f"rj_{uuid4().hex}",
            user_id=user_id,
            kind="thumbnail",
            target_replay_id=replay_id,
            target_match_id=replay.match_id,
            params_json=orjson.dumps(
                {
                    "start_tick": start_tick,
                    "end_tick": end_tick,
                    "scale": scale,
                    "theme": req.theme,
                }
            ).decode("utf-8"),
            cache_key=key,
            status="done",
            progress=100,
            ray_job_id=None,
            artifact_path=asset_key,
            error_message=None,
            created_at=now,
            finished_at=now,
        )
        db.add(job)
        db.commit()
        return RenderJobCreated(job_id=job.id, status=job.status, cache_key=key)  # type: ignore[arg-type]

    job = RenderJob(
        id=f"rj_{uuid4().hex}",
        user_id=user_id,
        kind="thumbnail",
        target_replay_id=replay_id,
        target_match_id=replay.match_id,
        params_json=orjson.dumps(
            {
                "start_tick": start_tick,
                "end_tick": end_tick,
                "scale": scale,
                "theme": req.theme,
            }
        ).decode("utf-8"),
        cache_key=key,
        status="queued",
        progress=0,
        ray_job_id=None,
        artifact_path=None,
        error_message=None,
        created_at=now,
        finished_at=None,
    )
    db.add(job)
    db.commit()

    if os.environ.get("NEUROLEAGUE_E2E_FAST") == "1":
        from neuroleague_api.render_runner import run_render_thumbnail_job

        run_render_thumbnail_job(
            job_id=job.id,
            replay_id=replay_id,
            start_tick=start_tick,
            end_tick=end_tick,
            scale=scale,
            theme=req.theme,
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
        )
        try:
            db.refresh(job)
        except Exception:  # noqa: BLE001
            pass
    elif settings.desktop_mode:
        pass
    else:
        ensure_ray()
        from neuroleague_api.ray_tasks import render_thumbnail_job

        obj_ref = render_thumbnail_job.remote(
            job_id=job.id,
            replay_id=replay_id,
            start_tick=start_tick,
            end_tick=end_tick,
            scale=scale,
            theme=req.theme,
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
        )
        job.ray_job_id = obj_ref.hex()
        db.add(job)
        db.commit()

    return RenderJobCreated(job_id=job.id, status=job.status, cache_key=key)  # type: ignore[arg-type]


@router.get("/{replay_id}/thumbnail", response_model=None)
def replay_thumbnail(
    replay_id: str,
    start: float = 0.0,
    end: float | None = None,
    scale: int = 1,
    theme: Literal["dark", "light"] = "dark",
    async_: int = Query(default=1, alias="async", ge=0, le=1),
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> Any:
    from neuroleague_api.clip_render import (
        cache_key,
        clamp_clip_params,
        render_thumbnail_png_bytes,
    )

    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")

    payload = load_replay_json(artifact_path=replay.artifact_path)
    digest = str(replay.digest or payload.get("digest") or "")
    if not digest:
        raise HTTPException(status_code=500, detail="Replay digest missing")

    start_tick, end_tick, _fps, scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=start,
        end_sec=end,
        fps=10,
        scale=scale,
        max_duration_sec=12.0,
    )
    key = cache_key(
        replay_digest=digest,
        kind="thumbnail",
        start_tick=start_tick,
        end_tick=end_tick,
        fps=1,
        scale=scale,
        theme=theme,
    )
    asset_key = f"clips/thumbnails/thumb_{replay_id}_{key[:16]}.png"
    cached = _asset_response(key=asset_key, media_type="image/png")
    if cached is not None:
        return cached

    if async_:
        created = create_thumbnail_job(
            replay_id=replay_id,
            req=ThumbnailJobRequest(start=start, end=end, scale=scale, theme=theme),
            user_id=user_id,
            db=db,
        )
        return JSONResponse(
            status_code=202,
            content={
                "job_id": created.job_id,
                "status": created.status,
                "cache_key": created.cache_key,
            },
        )

    backend = get_storage_backend()
    png = render_thumbnail_png_bytes(
        replay_payload=payload,
        start_tick=start_tick,
        end_tick=end_tick,
        scale=scale,
        theme=theme,
    )
    backend.put_bytes(key=asset_key, data=png, content_type="image/png")
    cached2 = _asset_response(key=asset_key, media_type="image/png")
    if cached2 is not None:
        return cached2
    raise HTTPException(status_code=500, detail="Failed to store thumbnail")


@router.get("/{replay_id}/clip", response_model=None)
def replay_clip(
    replay_id: str,
    start: float,
    end: float,
    format: Literal["webm", "gif", "mp4"] = "webm",
    fps: int = 12,
    scale: int = 1,
    theme: Literal["dark", "light"] = "dark",
    aspect: Literal["16:9", "9:16"] = "16:9",
    captions: bool = False,
    async_: int = Query(default=1, alias="async", ge=0, le=1),
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> Any:
    from neuroleague_api.clip_render import (
        CAPTIONS_VERSION,
        cache_key,
        captions_plan_for_segment,
        clamp_clip_params,
        render_gif_bytes,
        render_mp4_to_path,
        render_webm_to_path,
    )

    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")

    payload = load_replay_json(artifact_path=replay.artifact_path)
    digest = str(replay.digest or payload.get("digest") or "")
    if not digest:
        raise HTTPException(status_code=500, detail="Replay digest missing")

    start_tick, end_tick, fps, scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=start,
        end_sec=end,
        fps=fps,
        scale=scale,
        max_duration_sec=12.0,
    )
    kind = f"clip_{format}"
    captions_plan = (
        captions_plan_for_segment(
            replay_payload=payload, start_tick=start_tick, end_tick=end_tick
        )
        if captions
        else None
    )
    captions_lines = captions_plan.lines if captions_plan else None
    key = cache_key(
        replay_digest=digest,
        kind=kind,
        start_tick=start_tick,
        end_tick=end_tick,
        fps=fps,
        scale=scale,
        theme=theme,
        aspect=aspect,
        captions_version=(captions_plan.version or CAPTIONS_VERSION)
        if captions_plan
        else None,
        captions_template_id=captions_plan.template_id if captions_plan else None,
    )
    asset_key = f"clips/{format}/{kind}_{replay_id}_{key[:16]}.{format}"

    if format == "gif":
        media_type = "image/gif"
    elif format == "mp4":
        media_type = "video/mp4"
    else:
        media_type = "video/webm"

    cached = _asset_response(key=asset_key, media_type=media_type)
    if cached is not None:
        return cached

    if async_:
        created = create_clip_job(
            replay_id=replay_id,
            req=ClipJobRequest(
                start=start,
                end=end,
                format=format,
                fps=fps,
                scale=scale,
                theme=theme,
                aspect=aspect,
                captions=captions,
            ),
            user_id=user_id,
            db=db,
        )
        return JSONResponse(
            status_code=202,
            content={
                "job_id": created.job_id,
                "status": created.status,
                "cache_key": created.cache_key,
            },
        )

    backend = get_storage_backend()

    if format == "gif":
        gif = render_gif_bytes(
            replay_payload=payload,
            start_tick=start_tick,
            end_tick=end_tick,
            fps=fps,
            scale=scale,
            theme=theme,
            aspect=aspect,
            captions_lines=captions_lines,
        )
        backend.put_bytes(key=asset_key, data=gif, content_type=media_type)
    elif format == "mp4":
        local = backend.local_path(key=asset_key)
        if local is not None:
            render_mp4_to_path(
                replay_payload=payload,
                start_tick=start_tick,
                end_tick=end_tick,
                fps=fps,
                scale=scale,
                theme=theme,
                out_path=local,
                aspect=aspect,
                captions_lines=captions_lines,
            )
        else:
            from tempfile import TemporaryDirectory

            with TemporaryDirectory(prefix="neuroleague_mp4_") as tmpdir:
                tmp_path = Path(tmpdir) / f"{kind}_{replay_id}_{key[:16]}.mp4"
                render_mp4_to_path(
                    replay_payload=payload,
                    start_tick=start_tick,
                    end_tick=end_tick,
                    fps=fps,
                    scale=scale,
                    theme=theme,
                    out_path=tmp_path,
                    aspect=aspect,
                    captions_lines=captions_lines,
                )
                backend.put_file(key=asset_key, path=tmp_path, content_type=media_type)
    else:
        local = backend.local_path(key=asset_key)
        if local is not None:
            render_webm_to_path(
                replay_payload=payload,
                start_tick=start_tick,
                end_tick=end_tick,
                fps=fps,
                scale=scale,
                theme=theme,
                out_path=local,
                aspect=aspect,
                captions_lines=captions_lines,
            )
        else:
            from tempfile import TemporaryDirectory

            with TemporaryDirectory(prefix="neuroleague_webm_") as tmpdir:
                tmp_path = Path(tmpdir) / f"{kind}_{replay_id}_{key[:16]}.webm"
                render_webm_to_path(
                    replay_payload=payload,
                    start_tick=start_tick,
                    end_tick=end_tick,
                    fps=fps,
                    scale=scale,
                    theme=theme,
                    out_path=tmp_path,
                    aspect=aspect,
                    captions_lines=captions_lines,
                )
                backend.put_file(key=asset_key, path=tmp_path, content_type=media_type)

    cached2 = _asset_response(key=asset_key, media_type=media_type)
    if cached2 is not None:
        return cached2
    raise HTTPException(status_code=500, detail="Failed to store clip")


class ClipJobRequest(BaseModel):
    start: float
    end: float
    format: Literal["webm", "gif", "mp4"] = "webm"
    fps: int = Field(default=12, ge=5, le=30)
    scale: int = Field(default=1, ge=1, le=2)
    theme: Literal["dark", "light"] = "dark"
    aspect: Literal["16:9", "9:16"] = "16:9"
    captions: bool = False


@router.post("/{replay_id}/clip_jobs", response_model=RenderJobCreated)
def create_clip_job(
    replay_id: str,
    request: Request,
    req: ClipJobRequest,
    user_id: str = CurrentUserId,
    db: Session = DBSession,
) -> RenderJobCreated:
    from neuroleague_api.clip_render import (
        CAPTIONS_VERSION,
        captions_plan_for_segment,
        cache_key,
        clamp_clip_params,
    )
    from neuroleague_api.moderation import ensure_not_soft_banned

    replay = db.get(Replay, replay_id)
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    match = db.get(Match, replay.match_id)
    if not match or match.user_a_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")

    ensure_not_soft_banned(db, user_id=user_id)

    settings = Settings()
    check_rate_limit_dual(
        user_id=user_id,
        request=request,
        action="render_jobs",
        per_minute_user=int(settings.rate_limit_render_jobs_per_minute),
        per_hour_user=int(settings.rate_limit_render_jobs_per_hour),
        per_minute_ip=int(settings.rate_limit_render_jobs_per_minute_ip),
        per_hour_ip=int(settings.rate_limit_render_jobs_per_hour_ip),
        extra_detail={"kind": f"clip_{req.format}"},
    )

    payload = load_replay_json(artifact_path=replay.artifact_path)
    digest = str(replay.digest or payload.get("digest") or "")
    if not digest:
        raise HTTPException(status_code=500, detail="Replay digest missing")

    start_tick, end_tick, fps, scale = clamp_clip_params(
        replay_payload=payload,
        start_sec=req.start,
        end_sec=req.end,
        fps=req.fps,
        scale=req.scale,
        max_duration_sec=12.0,
    )
    kind = f"clip_{req.format}"
    captions_plan = (
        captions_plan_for_segment(
            replay_payload=payload, start_tick=start_tick, end_tick=end_tick
        )
        if req.captions
        else None
    )
    key = cache_key(
        replay_digest=digest,
        kind=kind,
        start_tick=start_tick,
        end_tick=end_tick,
        fps=fps,
        scale=scale,
        theme=req.theme,
        aspect=req.aspect,
        captions_version=(captions_plan.version or CAPTIONS_VERSION)
        if captions_plan
        else None,
        captions_template_id=captions_plan.template_id if captions_plan else None,
    )

    existing = db.scalar(
        select(RenderJob)
        .where(RenderJob.user_id == user_id)
        .where(RenderJob.cache_key == key)
        .order_by(RenderJob.created_at.desc())
        .limit(1)
    )
    if existing and existing.status in ("queued", "running", "done"):
        return RenderJobCreated(
            job_id=existing.id, status=existing.status, cache_key=key
        )  # type: ignore[arg-type]

    asset_key = f"clips/{req.format}/{kind}_{replay_id}_{key[:16]}.{req.format}"
    backend = get_storage_backend()
    now = datetime.now(UTC)
    if backend.exists(key=asset_key):
        job = RenderJob(
            id=f"rj_{uuid4().hex}",
            user_id=user_id,
            kind="clip",
            target_replay_id=replay_id,
            target_match_id=replay.match_id,
            params_json=orjson.dumps(
                {
                    "start_tick": start_tick,
                    "end_tick": end_tick,
                    "format": req.format,
                    "fps": fps,
                    "scale": scale,
                    "theme": req.theme,
                    "aspect": req.aspect,
                    "captions": bool(req.captions),
                    "captions_version": (captions_plan.version or CAPTIONS_VERSION)
                    if captions_plan
                    else None,
                    "captions_template_id": captions_plan.template_id
                    if captions_plan
                    else None,
                    "captions_event_type": captions_plan.event_type
                    if captions_plan
                    else None,
                }
            ).decode("utf-8"),
            cache_key=key,
            status="done",
            progress=100,
            ray_job_id=None,
            artifact_path=asset_key,
            error_message=None,
            created_at=now,
            finished_at=now,
        )
        db.add(job)
        db.commit()
        return RenderJobCreated(job_id=job.id, status=job.status, cache_key=key)  # type: ignore[arg-type]

    job = RenderJob(
        id=f"rj_{uuid4().hex}",
        user_id=user_id,
        kind="clip",
        target_replay_id=replay_id,
        target_match_id=replay.match_id,
        params_json=orjson.dumps(
            {
                "start_tick": start_tick,
                "end_tick": end_tick,
                "format": req.format,
                "fps": fps,
                "scale": scale,
                "theme": req.theme,
                "aspect": req.aspect,
                "captions": bool(req.captions),
                "captions_version": (captions_plan.version or CAPTIONS_VERSION)
                if captions_plan
                else None,
                "captions_template_id": captions_plan.template_id if captions_plan else None,
                "captions_event_type": captions_plan.event_type if captions_plan else None,
            }
        ).decode("utf-8"),
        cache_key=key,
        status="queued",
        progress=0,
        ray_job_id=None,
        artifact_path=None,
        error_message=None,
        created_at=now,
        finished_at=None,
    )
    db.add(job)
    db.commit()

    if os.environ.get("NEUROLEAGUE_E2E_FAST") == "1":
        from neuroleague_api.render_runner import run_render_clip_job

        run_render_clip_job(
            job_id=job.id,
            replay_id=replay_id,
            start_tick=start_tick,
            end_tick=end_tick,
            format=req.format,
            fps=fps,
            scale=scale,
            theme=req.theme,
            aspect=req.aspect,
            captions=bool(req.captions),
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
        )
        try:
            db.refresh(job)
        except Exception:  # noqa: BLE001
            pass
    elif settings.desktop_mode:
        pass
    else:
        ensure_ray()
        from neuroleague_api.ray_tasks import render_clip_job

        obj_ref = render_clip_job.remote(
            job_id=job.id,
            replay_id=replay_id,
            start_tick=start_tick,
            end_tick=end_tick,
            format=req.format,
            fps=fps,
            scale=scale,
            theme=req.theme,
            aspect=req.aspect,
            captions=bool(req.captions),
            db_url=settings.db_url,
            artifacts_dir=settings.artifacts_dir,
        )
        job.ray_job_id = obj_ref.hex()
        db.add(job)
        db.commit()

    return RenderJobCreated(job_id=job.id, status=job.status, cache_key=key)  # type: ignore[arg-type]
