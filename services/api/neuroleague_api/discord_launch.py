from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import orjson
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from neuroleague_api.build_of_day import (
    load_build_of_day_overrides,
    resolve_build_of_day,
)
from neuroleague_api.core.config import Settings
from neuroleague_api.models import Blueprint, Challenge, DiscordOutbox, FeaturedItem, Match, Replay
from neuroleague_api.quests_engine import kst_today_key, kst_week_key


DiscordMode = Literal["webhook", "app", "mock"]

KST = ZoneInfo("Asia/Seoul")


def _env_fallback(name: str) -> str | None:
    value = str(os.environ.get(name) or "").strip()
    return value or None


def discord_mode(settings: Settings | None = None) -> DiscordMode:
    settings = settings or Settings()
    raw = str(getattr(settings, "discord_mode", "") or "").strip() or str(
        _env_fallback("DISCORD_MODE") or "webhook"
    )
    raw = raw.lower().strip()
    if raw in {"webhook", "app", "mock"}:
        return raw  # type: ignore[return-value]
    return "webhook"


def discord_webhook_url(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    return str(
        getattr(settings, "discord_webhook_url", "") or ""
    ).strip() or _env_fallback("DISCORD_WEBHOOK_URL")


def discord_application_id(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    return str(
        getattr(settings, "discord_application_id", "") or ""
    ).strip() or _env_fallback("DISCORD_APPLICATION_ID")


def discord_public_key(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    return str(
        getattr(settings, "discord_public_key", "") or ""
    ).strip() or _env_fallback("DISCORD_PUBLIC_KEY")


def discord_bot_token(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    return str(
        getattr(settings, "discord_bot_token", "") or ""
    ).strip() or _env_fallback("DISCORD_BOT_TOKEN")


def discord_guild_id(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    return str(
        getattr(settings, "discord_guild_id", "") or ""
    ).strip() or _env_fallback("DISCORD_GUILD_ID")


def discord_channel_id(settings: Settings | None = None) -> str | None:
    settings = settings or Settings()
    return str(
        getattr(settings, "discord_channel_id", "") or ""
    ).strip() or _env_fallback("DISCORD_CHANNEL_ID")


def public_base_url(settings: Settings | None = None) -> str:
    settings = settings or Settings()
    base = str(getattr(settings, "public_base_url", "") or "").strip()
    return base.rstrip("/") if base else "http://127.0.0.1:3000"


def _daily_challenge_id(*, day_key: str, ruleset_version: str) -> str:
    raw = f"daily_challenge|{day_key}|{ruleset_version}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"ch_daily_{digest}"


@dataclass(frozen=True)
class DailyChallengePick:
    challenge_id: str
    replay_id: str | None


def ensure_daily_challenge(
    session: Session, *, now: datetime | None = None
) -> DailyChallengePick:
    settings = Settings()
    now_dt = now or datetime.now(UTC)
    day_key = kst_today_key(now_utc=now_dt)
    week_key = kst_week_key(now_utc=now_dt)
    cid = _daily_challenge_id(
        day_key=day_key, ruleset_version=str(settings.ruleset_version)
    )

    existing = session.get(Challenge, cid)
    if existing:
        return DailyChallengePick(
            challenge_id=str(existing.id),
            replay_id=str(existing.target_replay_id or "") or None,
        )

    # Prefer an active featured clip if present.
    feat = session.scalar(
        select(FeaturedItem)
        .where(FeaturedItem.kind == "clip")
        .where(FeaturedItem.status == "active")
        .where((FeaturedItem.starts_at.is_(None)) | (FeaturedItem.starts_at <= now_dt))
        .where((FeaturedItem.ends_at.is_(None)) | (FeaturedItem.ends_at > now_dt))
        .order_by(desc(FeaturedItem.priority), desc(FeaturedItem.created_at))
        .limit(1)
    )
    replay_id: str | None = str(feat.target_id) if feat and feat.target_id else None

    if replay_id and not session.get(Replay, replay_id):
        replay_id = None

    if replay_id is None:
        rows = session.execute(
            select(Replay.id)
            .join(Match, Match.id == Replay.match_id)
            .where(Match.status == "done")
            .where(Match.mode == "1v1")
            .where(Match.ruleset_version == str(settings.ruleset_version))
            .order_by(desc(Match.created_at), desc(Match.id))
            .limit(80)
        ).all()
        cand = [str(rid) for (rid,) in rows if rid]
        if cand:
            seed = hashlib.sha256(
                f"{day_key}|{settings.ruleset_version}".encode("utf-8")
            ).hexdigest()
            cand.sort(
                key=lambda rid: hashlib.sha256(
                    f"{seed}|{rid}".encode("utf-8")
                ).hexdigest()
            )
            replay_id = cand[0]

    if replay_id is None and session.get(Replay, "r_seed_001"):
        replay_id = "r_seed_001"

    start_sec: float | None = 0.0
    end_sec: float | None = None
    if replay_id:
        try:
            from neuroleague_api.clip_render import best_clip_segment
            from neuroleague_api.storage import load_replay_json

            rp = session.get(Replay, replay_id)
            if rp:
                payload = load_replay_json(artifact_path=rp.artifact_path)
                st, et = best_clip_segment(payload, max_duration_sec=12.0)
                start_sec = float(st) / 20.0
                end_sec = float(et) / 20.0
        except Exception:  # noqa: BLE001
            start_sec, end_sec = 0.0, None

    ch = Challenge(
        id=cid,
        kind="clip",
        target_blueprint_id=None,
        target_replay_id=replay_id,
        start_sec=start_sec,
        end_sec=end_sec,
        mode="1v1",
        ruleset_version=str(settings.ruleset_version),
        week_id=str(week_key),
        portal_id=None,
        augments_a_json="[]",
        augments_b_json="[]",
        creator_user_id=None,
        status="active",
        created_at=now_dt,
    )
    session.add(ch)

    # Feature the daily challenge for home/feed integrations.
    session.add(
        FeaturedItem(
            id=f"fi_{uuid4().hex}",
            kind="challenge",
            target_id=cid,
            title_override="Daily Challenge",
            priority=1000,
            starts_at=now_dt,
            ends_at=now_dt + timedelta(days=1),
            status="active",
            created_at=now_dt,
            created_by="discord",
        )
    )
    session.flush()
    return DailyChallengePick(challenge_id=cid, replay_id=replay_id)


def build_daily_post_payload(
    session: Session, *, now: datetime | None = None
) -> dict[str, Any]:
    settings = Settings()
    now_dt = now or datetime.now(UTC)
    base = public_base_url(settings)
    day_key = kst_today_key(now_utc=now_dt)

    daily = ensure_daily_challenge(session, now=now_dt)
    challenge_url = f"{base}/s/challenge/{daily.challenge_id}"

    clip_url: str | None = None
    if daily.replay_id:
        try:
            from neuroleague_api.clip_render import best_clip_segment
            from neuroleague_api.storage import load_replay_json

            replay = session.get(Replay, daily.replay_id)
            if replay:
                payload = load_replay_json(artifact_path=replay.artifact_path)
                start_tick, end_tick = best_clip_segment(payload, max_duration_sec=12.0)
                s = float(start_tick) / 20.0
                e = float(end_tick) / 20.0
                q = f"start={s:.1f}&end={e:.1f}&v=1"
                clip_url = f"{base}/s/clip/{daily.replay_id}?{q}"
                clip_thumb_url = f"{base}/s/clip/{daily.replay_id}/thumb.png?start={s:.1f}&end={e:.1f}&scale=1&theme=dark"
            else:
                clip_thumb_url = None
        except Exception:  # noqa: BLE001
            clip_url = f"{base}/s/clip/{daily.replay_id}?v=1"
            clip_thumb_url = None
    else:
        clip_thumb_url = None

    build_id: str | None = None
    try:
        bod_overrides = load_build_of_day_overrides()
        bod = resolve_build_of_day(
            session,
            date_key=day_key,
            mode="1v1",
            ruleset_version=settings.ruleset_version,
            overrides=bod_overrides,
        )
        build_id = bod.picked_blueprint_id
    except Exception:  # noqa: BLE001
        build_id = None

    if not build_id:
        feat_build = session.scalar(
            select(FeaturedItem)
            .where(FeaturedItem.kind == "build")
            .where(FeaturedItem.status == "active")
            .where(
                (FeaturedItem.starts_at.is_(None)) | (FeaturedItem.starts_at <= now_dt)
            )
            .where((FeaturedItem.ends_at.is_(None)) | (FeaturedItem.ends_at > now_dt))
            .order_by(desc(FeaturedItem.priority), desc(FeaturedItem.created_at))
            .limit(1)
        )
        build_id = (
            str(feat_build.target_id) if feat_build and feat_build.target_id else None
        )

    if not build_id:
        build_id = "bp_demo_1v1"
    build_url = f"{base}/s/build/{build_id}"

    weekly_url = f"{base}/tournament"

    remix_url = f"{base}/start?next={quote(f'/forge?bp={build_id}', safe='')}"
    build_code: str | None = None
    try:
        bp = session.get(Blueprint, build_id)
        if bp:
            build_code = str(bp.build_code or "").strip() or None
            if build_code is None and bp.spec_json:
                from neuroleague_api.build_code import encode_build_code
                from neuroleague_sim.models import BlueprintSpec
                from neuroleague_sim.pack_loader import active_pack_hash

                spec = BlueprintSpec.model_validate(orjson.loads(bp.spec_json))
                build_code = encode_build_code(spec=spec, pack_hash=active_pack_hash())
                bp.build_code = build_code
                session.add(bp)
    except Exception:  # noqa: BLE001
        build_code = None

    embeds: list[dict[str, Any]] = []
    if clip_url:
        clip_embed: dict[str, Any] = {
            "title": "Top Clip Today",
            "description": "Watch and remix the top moment.",
            "url": clip_url,
        }
        if clip_thumb_url:
            clip_embed["image"] = {"url": clip_thumb_url}
        embeds.append(clip_embed)
    embeds.append(
        {
            "title": "Build of the Day",
            "description": "Open the featured build and hit Ranked.",
            "url": build_url,
        }
    )
    embeds.append(
        {
            "title": "Beat This (Daily Challenge)",
            "description": "Can you beat it? Accept the daily challenge.",
            "url": challenge_url,
        }
    )
    embeds.append(
        {
            "title": "This Week",
            "description": "Weekly theme + tournament queue.",
            "url": weekly_url,
        }
    )

    buttons: list[dict[str, Any]] = []
    if clip_url:
        buttons.append({"type": 2, "style": 5, "label": "Watch Clip", "url": clip_url})
    buttons.append({"type": 2, "style": 5, "label": "Remix", "url": remix_url})
    buttons.append({"type": 2, "style": 5, "label": "Build", "url": build_url})
    buttons.append({"type": 2, "style": 5, "label": "Beat This", "url": challenge_url})
    buttons.append({"type": 2, "style": 5, "label": "Weekly", "url": weekly_url})

    content_lines = [f"NeuroLeague Daily Drop · {day_key}"]
    content_lines.append(f"Beat This: {challenge_url}")
    content_lines.append(f"Remix: {remix_url}")
    if build_code:
        content_lines.append(f"Build Code: {build_code}")
    content = "\n".join(content_lines)
    if len(content) > 1900:
        content = "\n".join(content_lines[:3])

    return {
        "content": content,
        "embeds": embeds[:10],
        "components": [{"type": 1, "components": buttons[:5]}],
    }


def enqueue_discord_outbox(
    session: Session, *, kind: str, payload: dict[str, Any], now: datetime | None = None
) -> DiscordOutbox:
    now_dt = now or datetime.now(UTC)
    row = DiscordOutbox(
        id=f"do_{uuid4().hex}",
        kind=str(kind),
        payload_json=orjson.dumps(payload).decode("utf-8"),
        status="queued",
        attempts=0,
        next_attempt_at=None,
        last_error=None,
        created_at=now_dt,
        sent_at=None,
    )
    session.add(row)
    session.flush()
    return row


@dataclass(frozen=True)
class SendResult:
    ok: bool
    status_code: int | None = None
    retry_after_sec: float | None = None
    error: str | None = None


def _webhook_url_for_kind(settings: Settings, *, kind: str) -> str | None:
    if str(kind) == "alert":
        url = str(getattr(settings, "alerts_discord_webhook_url", "") or "").strip()
        return url or discord_webhook_url(settings)
    return discord_webhook_url(settings)


def _send_payload(settings: Settings, *, kind: str, payload: dict[str, Any]) -> SendResult:
    mode = discord_mode(settings)
    if mode == "mock":
        return SendResult(ok=True, status_code=200)

    if mode == "webhook":
        url = _webhook_url_for_kind(settings, kind=kind)
        if not url:
            return SendResult(ok=False, error="missing_webhook_url")
        try:
            resp = httpx.post(url, json=payload, timeout=10.0)
        except Exception as exc:  # noqa: BLE001
            return SendResult(ok=False, error=str(exc)[:300])
        if resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            try:
                return SendResult(
                    ok=False,
                    status_code=429,
                    retry_after_sec=float(ra or 1.0),
                    error="rate_limited",
                )
            except Exception:  # noqa: BLE001
                return SendResult(
                    ok=False, status_code=429, retry_after_sec=1.0, error="rate_limited"
                )
        if 200 <= resp.status_code < 300:
            return SendResult(ok=True, status_code=resp.status_code)
        return SendResult(ok=False, status_code=resp.status_code, error=resp.text[:400])

    # app mode
    token = discord_bot_token(settings)
    channel = discord_channel_id(settings)
    if not token or not channel:
        return SendResult(ok=False, error="missing_bot_config")
    url = f"https://discord.com/api/v10/channels/{channel}/messages"
    try:
        resp = httpx.post(
            url, json=payload, headers={"Authorization": f"Bot {token}"}, timeout=10.0
        )
    except Exception as exc:  # noqa: BLE001
        return SendResult(ok=False, error=str(exc)[:300])
    if resp.status_code == 429:
        ra = resp.headers.get("Retry-After")
        try:
            return SendResult(
                ok=False,
                status_code=429,
                retry_after_sec=float(ra or 1.0),
                error="rate_limited",
            )
        except Exception:  # noqa: BLE001
            return SendResult(
                ok=False, status_code=429, retry_after_sec=1.0, error="rate_limited"
            )
    if 200 <= resp.status_code < 300:
        return SendResult(ok=True, status_code=resp.status_code)
    return SendResult(ok=False, status_code=resp.status_code, error=resp.text[:400])


def process_outbox(
    session: Session, *, limit: int = 10, now: datetime | None = None
) -> dict[str, Any]:
    settings = Settings()
    now_dt = now or datetime.now(UTC)

    rows = session.scalars(
        select(DiscordOutbox)
        .where(DiscordOutbox.status == "queued")
        .where(
            (DiscordOutbox.next_attempt_at.is_(None))
            | (DiscordOutbox.next_attempt_at <= now_dt)
        )
        .order_by(DiscordOutbox.created_at.asc())
        .limit(int(limit))
        .with_for_update(skip_locked=True)
    ).all()
    if not rows:
        return {"ok": True, "processed": 0}

    processed = 0
    sent = 0
    failed = 0
    retried = 0
    for row in rows:
        processed += 1
        try:
            payload = orjson.loads((row.payload_json or "{}").encode("utf-8"))
            payload = payload if isinstance(payload, dict) else {}
        except Exception:  # noqa: BLE001
            payload = {}

        res = _send_payload(settings, kind=str(row.kind or ""), payload=payload)
        row.attempts = int(row.attempts or 0) + 1
        if res.ok:
            row.status = "sent"
            row.sent_at = now_dt
            row.last_error = None
            row.next_attempt_at = None
            sent += 1
            session.add(row)
            continue

        row.last_error = str(res.error or "send_failed")[:400]
        if res.status_code == 429 and res.retry_after_sec is not None:
            row.status = "queued"
            row.next_attempt_at = now_dt + timedelta(seconds=float(res.retry_after_sec))
            retried += 1
            session.add(row)
            continue

        if int(row.attempts or 0) >= 8:
            row.status = "failed"
            row.next_attempt_at = None
            failed += 1
            session.add(row)
            continue

        backoff = min(3600.0, float(2 ** max(0, int(row.attempts or 1) - 1)))
        row.status = "queued"
        row.next_attempt_at = now_dt + timedelta(seconds=backoff)
        retried += 1
        session.add(row)

        # Tiny sleep to avoid hammering on fast retries in a tight loop.
        time.sleep(0.05)

    return {
        "ok": True,
        "processed": processed,
        "sent": sent,
        "failed": failed,
        "retried": retried,
    }


def should_send_daily_post(session: Session, *, now: datetime | None = None) -> bool:
    settings = Settings()
    mode = discord_mode(settings)
    if mode == "mock":
        return False

    now_dt = now or datetime.now(UTC)
    hour = int(getattr(settings, "discord_daily_post_hour_kst", 9) or 9)
    kst_now = now_dt.astimezone(KST)
    if int(kst_now.hour) < int(hour):
        return False

    day_key = kst_today_key(now_utc=now_dt)
    # Has a daily_post already been sent for this KST day?
    last = session.scalar(
        select(DiscordOutbox.created_at)
        .where(DiscordOutbox.kind == "daily_post")
        .where(DiscordOutbox.status == "sent")
        .order_by(desc(DiscordOutbox.created_at))
        .limit(1)
    )
    if last is None:
        return True
    try:
        last_day = (
            (last.replace(tzinfo=UTC)).astimezone(KST).date().strftime("%Y-%m-%d")
        )
    except Exception:  # noqa: BLE001
        return True
    return last_day != day_key
